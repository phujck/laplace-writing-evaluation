"""DEVELOPMENT SOURCE (in-harness join; causal correction J-R1..J-R3, 2026-10-20): a configured repository becomes
writable code under ONE authoritative local Work grant, with exact reads, a durable recoverable apply transaction and
an input-scoped, budgeted, turn-owned isolated check.

AUTHORITY (J-R1; residual closure J-R1-R1, Root decision BOOTSTRAP). The resource is a repository configured for the
project (writing_sources). Discovery is not write authority, and neither is a native work turn: the ROOT GRANT is
issued only through the authenticated human/admin owner boundary (the human door: POST /work/development), a Work
ledger row (project-work-phase, kind development-grant) that binds
  the repository id and its configured real checkout, the checkout's base commit (core.versioning.head_sha),
  the Work id and its material scope revision (project_work._work_basis),
  the exact PARENT SESSION the authority is issued to (an author-role session of this project), the required
  EVALUATOR (an approved review binding of this Work, writing.work_delivery), the explicit DELEGATES (child session
  ids, each with the bounded subset it may use), the permitted path globs, operation kinds, check profiles and a
  finite lifetime.
A grant is minted once per stable request_id: a replay answers the existing grant (no new expiry, no new actor).
A native turn can neither issue nor reissue a root grant; the authorised PARENT SESSION may `delegate` a bounded
SUBSET of its own grant (operations and paths that only narrow) to an actual child session it opened, under the
same grant row; nothing widens. Consumption (`_current`) revalidates everything on every call: state and lifetime,
operation, Work scope revision, the RE-RESOLVED configured resource (an alias or registry change refuses), the
checkout base, the evaluator binding, the protected roots, and the acting identity: human; the parent session; a
delegate session within its subset; or, for `read` only, the reviewer session an ADMITTED delivery to the evaluator
binding opened. An unrelated turn of the same project is refused. Protected roots (the serving checkout, the
canonical Main root, the project's author drafts) are refused both as a checkout and as a target reached through an
ancestor checkout.

EFFECT (J-R2). `apply` is one durable transaction per candidate (effect id = digest of the candidate id): the
PREPARED row (every file's exact original and intended postimage, the original actor) is appended BEFORE any byte
moves; files are written under the physical source lease (manuscript_source.source_mutation), each one
conditionally: a file already at its postimage is ALREADY_APPLIED, a file at its preimage is written (COMMITTED), any
other bytes are DIVERGED and never overwritten; a failed write compensates this attempt's own writes only where the
file still holds this operation's postimage (ROLLED_BACK), otherwise DIVERGED. The published row states COMMITTED,
PARTIAL or ROLLED_BACK with per-file states and the shared source-effect receipt. A retry of the same candidate after
a write, append or crash cut reconciles each actual file state and recovers the SAME request under the original
attribution; nothing demands a new candidate to hide an unbanked earlier write.

CHECK (J-R3; residual closure J-R3-R1, Root decision WRITABLE_BOUND). A check consumes exact inputs: the profile's
`inputs` globs (within the grant's paths) are materialised through the same fence into a private staging tree with
their pins recorded (optionally asserted equal to a candidate's postimages); nothing else of the checkout is visible
(.git, credential-shaped and out-of-grant files are absent by construction). The launcher is bubblewrap
(--unshare-all, --die-with-parent, read-only /usr and staging, cleared environment) and the ONLY writable place is a
size-bounded isolated scratch filesystem (tmpfs at /tmp, `scratch_bytes`): no host directory is mounted writable, so
the aggregate writable budget holds DURING execution (ENOSPC at the bound); the scratch dies with the namespace and
the owner publishes only the bounded stdout (`max_output_bytes`) after execution. Scratch units: bytes, whole pages of
SCRATCH_PAGE (os page size) between SCRATCH_MIN and SCRATCH_MAX; every file consumes at least one page; an unaligned
or out-of-range budget is REFUSED at grant, never rounded. The other budgets are enforced by the OS: RLIMIT_CPU
(timeout), RLIMIT_AS (memory), RLIMIT_NPROC (processes), RLIMIT_FSIZE (any one file, = scratch), RLIMIT_NOFILE, a
wall clock and the stdout cap. Cancellation
and ownership go through the real turn/control path: the acting turn's live job (interrupt_requested/done), the
child host's cancel marker, the grant's revocation and any change of the execution generation the check joined
(session, turn, host birth identity) all stop the process group; a native actor's check is registered with
child_hosts as an AUXILIARY process of that generation (provider facts untouched), from whichever process runs the
call, so interrupt_turn and the Source governor terminate it; a native actor with no live hosted execution is refused
before launch. If any enforcement is unavailable (no launcher, no --size, no resource limits) the check is
UNAVAILABLE before launch; it never runs bare.

Separation: candidate, check and independent review are different obligations; source acceptance is not promotion;
nothing here touches manuscript selection, drafts, preferences, the app service or publication.

PREPARED COMPLETION (Eigen continuity, Root e716/a6d0). `arm` lets the genuine ACTIVE producer (an author turn of the
grant's original parent session, attached to its opted-in commission, before that turn ends) record ONE immutable
completion intent: exact cumulative pins (every path changed by any committed effect of the grant plus every declared
obligation input), the qualified review basis, original actor/session/turn/commission, the approved evaluator binding,
return policy and typed peer-proof slots. `proof` attaches one exact retained project Artifact to a declared slot: an
arrival fact, never a review or acceptance. Both are rows of this Work's development tuple; readiness and the one
Continue belong to laplace.work.project_work_continuity and work_delivery. Grant/read/candidate/apply/check guards are
unchanged, and neither action renews write authority.
"""
from __future__ import annotations

import datetime as dt
import copy
import fnmatch
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

RECORD = 'project-work-phase'
KINDS = {'grant': 'development-grant', 'candidate': 'development-candidate', 'effect': 'development-effect', 'check': 'development-check',
         'lane': 'development-lane'}
OPERATIONS = ('read', 'candidate', 'apply', 'check')
# A DEVELOPMENT LANE (wave 13, dev-route packet 1; incorporation D4/D6): a lean worktree of the serving checkout cut for one
# Work, held by its development-lane row (id lane:<work-id>, the latest row wins). The row is the only record that says a
# lane is a grantable checkout: no lanes file, and profiles/writing_sources.json is never edited by the app.
LANE_STATES = ('ACTIVE', 'ADOPTED', 'DISCARDED')
LANE_PREFIX = 'lane:'
LANE_PATHS = ('src/**', 'tests/**', 'scripts/**', 'profiles/**')
LANE_SCRIPT = Path('scripts/sparse_worktree.sh')          # serving-checkout relative; run with its fourth argument "lean"
LANE_HOME_ENV = 'LAPLACE_DEV_LANE_HOME'                   # a test or scenario puts lanes under its own temporary root
LANE_HOME = Path('~/.local/share/laplace/worktrees/app-dev')
# Assumption (labelled): a lane serves one day of a development session; the human door names lifetime_s (60 s to
# MAX_LIFETIME_S) for anything else. An ordinary grant's default stays 3600 s (grant, issue body).
LANE_LIFETIME_S = 24 * 3600
# Measured 2026-11-08: a lean cut of the app source took about 3 s (70 MB); 300 s is 100x that, room for a cold disk cache,
# and the same bound as node-suite's timeout_s in profiles/development_checks.json.
LANE_CUT_TIMEOUT_S = 300
CHECK_PROFILES = Path('profiles/development_checks.json')   # root relative: the fixed check profiles a lane grant carries
CHECK_PROFILES_SCHEMA = 'laplace.development-check-profiles/1'
FAILURE_PARSERS = ('tap', 'pytest')
# Derived: the owner's existing bound on a check's named file lists (MAX_CHECK_DEPENDENCIES and fixed_inputs maxProperties, 64).
MAX_CHECK_TARGETS = 64
# Derived from the delivery line: the 64 names of the measured node-suite run (judge-r1) are 4,634 JSON bytes (72 a name), so one check
# row's list stays under a quarter of the 30,000-byte status line; failing_total counts the rest and output_read holds them all.
MAX_FAILING_NAMES = 64
MAIN_ROOT = Path('/home/phujck/VScodeProjects/laplace')
MAX_LIFETIME_S = 7 * 24 * 3600
MAX_CANDIDATE_BYTES = 256 * 1024
MAX_COMPACT_EDITS = 64
REVIEW_BASIS_SCHEMA = 'laplace.development-review-basis/1'
VERIFIED_EDITS_SCHEMA = 'laplace.development-verified-edits/1'
REVIEW_PLAN_SCHEMA = 'laplace.development-review-plan/1'
REVIEW_PAGE_CHARS = 6000
MAX_REVIEW_WINDOWS = 64
#: The canonical CUMULATIVE review subject (closure contract 2026-11-02): every COMMITTED effect of the commission
#: across its reissued grants, an explicitly admitted READ-ONLY carry manifest and a typed acceptance stage. The latest
#: candidate/effect stays the exact anchor and latest delta; it no longer defines the review scope. Plan v1 rows keep
#: their original meaning (latest candidate only) and remain readable.
REVIEW_SUBJECT_SCHEMA = 'laplace.development-review-subject/1'
REVIEW_CARRY_SCHEMA = 'laplace.development-review-carry/1'
REVIEW_PLAN_SCHEMA_V2 = 'laplace.development-review-plan/2'
REVIEW_PLAN_SCHEMAS = (REVIEW_PLAN_SCHEMA, REVIEW_PLAN_SCHEMA_V2)
MAX_SUBJECT_HUNKS = 256
MAX_STAGE_CRITERIA = 16
MAX_STAGE_TEXT = 600
MAX_STAGE_SUMMARY = 2000
MAX_STAGE_AUTHORITY = 8
_SHA = re.compile(r'sha256:[0-9a-f]{64}')
MAX_CHECK_WALL_S = 600
MAX_CHECK_OUTPUT = 1024 * 1024
MAX_CHECK_MEMORY = 2 * 1024 ** 3
MAX_CHECK_PROCESSES = 64
TAIL_BYTES = 4096
PAGE = 8
STATUS_PARTS = ('grants', 'candidates', 'effects', 'checks')
SCRATCH_PAGE = os.sysconf('SC_PAGE_SIZE') if hasattr(os, 'sysconf') else 4096
SCRATCH_MIN = SCRATCH_PAGE
SCRATCH_MAX = 64 * 1024 ** 2
SCRATCH = Path('/tmp')   # the one writable place inside a check: an isolated, size-bounded tmpfs
#: The ONE fixed, neutral sandbox-local location of a check's staged inputs and its working directory: the exact verified
#: host stage is bound read-only HERE (a sibling of the scratch, never under it). The host stage path itself is not mounted
#: inside the sandbox; host custody (output_root, the stage, its pins and cleanup) stays on the host.
SANDBOX_INPUT = Path('/input')
CREDENTIAL_NAMES = ('.env', '.netrc', '.npmrc', '.pypirc', 'id_rsa', 'id_ed25519', 'credentials', 'secrets')
CREDENTIAL_SUFFIXES = ('.pem', '.key', '.token', '.p12', '.pfx')
RUNTIME_MOUNT = Path('/usr')
#: A check profile's runtime (Root aef8df7c): 'system' is the legacy interpreter named by an absolute path under the
#: read-only /usr mount; 'registered-python' is the serving root's REGISTERED lifecycle interpreter (laplace.core.runtime
#: declaration), named only by the role executable 'python', with its exact admission basis recorded on the grant.
REGISTERED_RUNTIME = 'registered-python'
RUNTIME_KINDS = ('system', REGISTERED_RUNTIME)
RUNTIME_ADMISSION_SCHEMA = 'laplace.check-runtime-admission/1'
MAX_CHECK_DEPENDENCIES = 64
#: The read-only dependency CLOSURE of a check (Root decision after DK-fc42cebfae7e1778321f2c45): an immutable pinned
#: manifest, inline or a project Artifact reference pinned by sha256, validated ONCE at grant, recorded on the grant row
#: and staged member by member read-only at check. The inline `dependencies` map stays a small convenience, not a
#: semantic test-size ceiling. Bounds are explicit and reported; a member never gains Source write authority.
DEPENDENCY_MANIFEST_SCHEMA = 'laplace.check-dependency-manifest/1'
DEPENDENCY_MANIFEST_SCHEMAS = (DEPENDENCY_MANIFEST_SCHEMA, 'laplace.observed-public-check-dependency-closure/1')
MAX_DEPENDENCY_MANIFEST_MEMBERS = 4096
MAX_DEPENDENCY_CLOSURE_BYTES = 256 * 1024 ** 2


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# ------------------------------------------------------------------------------------------------ the current coordination entry
#: The one owned home of the CURRENT development coordination run (the sole mutable run the coordinator writes), inside
#: the checkout's Work data root. Historical grants, returns and pins stay where they were written.
COORDINATION_HOME = Path('corpus_friction/development/current.json')
#: Where the current run lived before its home existed; read only while the home is absent (an older layout). The
#: coordinator's move archives this file under a pinned historical name, so it stays out of the current set.
COORDINATION_LEGACY = (Path('evidence/WRITING_JOINS_2026-10-04/codex-continuation/source-state-development-run-20261019.json'),)


def coordination_entry(root: Path) -> dict:
    """Which file is the current development coordination run, and its bounded identity (never its whole body).

    The owned home wins; a legacy location is read only while the home is absent; a run present in both is refused,
    because the coordinator's move left two current copies. Nothing is written or moved here."""
    root = Path(root)
    home = root / COORDINATION_HOME
    legacy = [root / rel for rel in COORDINATION_LEGACY if (root / rel).is_file()]
    if home.is_file() and legacy:
        raise ValueError('Two current development runs: %s and %s. Finish the move in docs/operational-homes.md: '
                         'archive the legacy file in its own directory under its pinned historical name '
                         '(source-state-development-run-<date>.historical-<UTC stamp>.json, byte-verified), so only the home '
                         'is current.' % (COORDINATION_HOME, legacy[0].relative_to(root)))
    selected = home if home.is_file() else (legacy[0] if legacy else None)
    entry = {'schema_version': 'laplace.development-coordination-entry/1', 'home': COORDINATION_HOME.as_posix(),
             'legacy': [rel.as_posix() for rel in COORDINATION_LEGACY], 'selected': None, 'path': None}
    if selected is None:
        return entry
    raw = selected.read_bytes()
    record = json.loads(raw)
    return {**entry, 'selected': 'home' if selected == home else 'legacy', 'path': selected.relative_to(root).as_posix(),
            'sha256': 'sha256:' + hashlib.sha256(raw).hexdigest(), 'schema': record.get('schema'),
            'status': record.get('status'), 'current_work': record.get('current_work'), 'at': record.get('at')}


def _digest(value: Any) -> str:
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


PREIMAGE_PIN = {'oneOf': [{'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'}, {'type': 'null'}],
                'description': ('The exact current pin that read returns for this path: sha256:<64 lowercase hex> of the whole current '
                                'file, or null only to create a file that does not exist yet. A bare digest or any other spelling is '
                                'refused by this contract; a well-formed but stale pin refuses as a preimage mismatch, so read again.')}


def contract() -> dict:
    """The declared payload: one action per call; the owner enforces each action's required fields (the schema stays
    one small object so the default help carries it inline)."""
    string = {'type': 'string'}
    profile = {'type': 'object', 'required': ['executable', 'args', 'inputs'], 'additionalProperties': False,
               'properties': {'executable': string, 'args': {'type': 'array', 'items': string, 'maxItems': 32},
                              'inputs': {'type': 'array', 'items': string, 'minItems': 1, 'maxItems': 32},
                              'timeout_s': {'type': 'integer', 'minimum': 1, 'maximum': MAX_CHECK_WALL_S},
                              'max_output_bytes': {'type': 'integer', 'minimum': 1024, 'maximum': MAX_CHECK_OUTPUT},
                              'scratch_bytes': {'type': 'integer', 'minimum': SCRATCH_MIN, 'maximum': SCRATCH_MAX},
                              'memory_bytes': {'type': 'integer', 'minimum': 16 * 1024 ** 2, 'maximum': MAX_CHECK_MEMORY},
                              'max_processes': {'type': 'integer', 'minimum': 1, 'maximum': MAX_CHECK_PROCESSES}}}
    profile['properties']['targets'] = {'type': 'array', 'items': string, 'minItems': 1, 'maxItems': 16,
        'description': 'Globs a check call may name in targets (appended after the fixed argv); each lies within inputs.'}
    profile['properties']['requires_targets'] = {'type': 'boolean', 'description': 'A check of this profile names at least one target.'}
    profile['properties']['sandbox_differences'] = {'type': 'array', 'maxItems': MAX_FAILING_NAMES, 'items': {
        'type': 'object', 'required': ['name', 'cause'], 'additionalProperties': False, 'properties': {'name': string, 'cause': string}},
        'description': ('Failing names the profile owner measured to fail only inside the check sandbox, each with its cause; '
                        'the check row repeats each with failed true or false for that run. The runner output stays the truth.')}
    profile['properties']['failures'] = {'enum': list(FAILURE_PARSERS),
        'description': "How failing test names are read from the runner's own output: tap ('not ok N - name') or pytest ('FAILED|ERROR nodeid')."}
    profile['properties']['fixed_inputs'] = {'type': 'object', 'maxProperties': 64,
        'additionalProperties': {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'}}
    profile['properties']['dependencies'] = {'type': 'object', 'maxProperties': MAX_CHECK_DEPENDENCIES,
        'additionalProperties': {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'},
        'description': ('Exact READ-ONLY check dependencies {checkout-relative path: sha256 pin} outside the writable grant paths: '
                        'validated (no symlink component, inside the checkout, not git internals or credential-shaped) and pinned at '
                        'grant and again before staging, then staged read-only beside the inputs. Never writable by candidate/apply. '
                        'A missing, changed, symlinked or escaping dependency refuses the whole check; nothing is silently skipped.')}
    profile['properties']['runtime'] = {'enum': list(RUNTIME_KINDS), 'default': 'system',
        'description': ('system: executable is an absolute path under the read-only /usr mount (legacy). registered-python: executable '
                        'is the role name "python", resolved from the serving root runtime_profiles.toml lifecycle declaration (never '
                        'LAPLACE_PYTHON, a caller path or the candidate checkout); its admission basis is recorded at grant and must '
                        'match at check, and its prefix is mounted read-only.')}
    member = {'type': 'object', 'required': ['path', 'sha256'], 'additionalProperties': False,
              'properties': {'path': string, 'sha256': {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'}, 'bytes': {'type': 'integer', 'minimum': 0}}}
    profile['properties']['dependency_manifest'] = {'oneOf': [
        {'type': 'object', 'additionalProperties': False, 'required': ['schema', 'members'],
         'properties': {'schema': {'enum': list(DEPENDENCY_MANIFEST_SCHEMAS)},
                        'members': {'type': 'array', 'minItems': 1, 'maxItems': MAX_DEPENDENCY_MANIFEST_MEMBERS, 'items': member}}},
        {'type': 'object', 'additionalProperties': False, 'required': ['artifact_id', 'expected_sha256'],
         'properties': {'artifact_id': {'type': 'string', 'pattern': '^ART-'}, 'expected_sha256': {'type': 'string', 'pattern': '^(sha256:)?[0-9a-f]{64}$'}}}],
        'description': ('The read-only check dependency CLOSURE as one immutable pinned manifest: inline {schema, members:[{path, sha256}]} '
                        'or a project Artifact {artifact_id, expected_sha256} holding that JSON. Validated once at grant (every member '
                        'present, real, unchanged, fenced, never a writable grant path; at most %d members and %d bytes), recorded on '
                        'the grant, revalidated and staged read-only at check with its coverage. Not a widening of write authority.'
                        % (MAX_DEPENDENCY_MANIFEST_MEMBERS, MAX_DEPENDENCY_CLOSURE_BYTES))}
    file = {'type': 'object', 'required': ['path', 'before_sha256'], 'additionalProperties': False,
        'properties': {'path': string, 'before_sha256': PREIMAGE_PIN, 'content': string,
            'edits': {'type': 'array', 'minItems': 1, 'maxItems': MAX_COMPACT_EDITS,
                'items': {'type': 'object', 'required': ['old', 'new'], 'additionalProperties': False,
                    'properties': {'old': {'type': 'string', 'minLength': 1}, 'new': string}}}},
        'oneOf': [{'required': ['content'], 'not': {'required': ['edits']}},
                  {'required': ['edits'], 'not': {'required': ['content']}}]}
    from laplace.writing import source_execution
    from laplace.work import project_work_continuity
    allowance = {'type': 'object', 'additionalProperties': False, 'required': sorted(source_execution.POLICY_FIELDS),
        'properties': {'commission_request_id': {'type': 'string', 'pattern': '^[A-Za-z0-9._:-]{8,96}$'},
            **{key: {'type': 'integer', 'minimum': 1, 'maximum': MAX_LIFETIME_S if key == 'wall_seconds' else source_execution.SAFE_INTEGER} for key in source_execution.LIMITS}}}
    return {'schema_version': 'laplace.development-source-contract/2', 'type': 'object', 'required': ['action'], 'additionalProperties': False,
            'properties': {'project': string, 'action': {'enum': ['grant', 'delegate', 'revoke', 'read', 'candidate', 'apply', 'check', 'status', 'arm', 'proof', 'review-preflight', 'lane', 'discard']},
                           'targets': {'type': 'array', 'items': string, 'minItems': 1, 'maxItems': MAX_CHECK_TARGETS},
                           'branch': string,
                           'check_id': {'type': 'string', 'pattern': '^DK-[0-9a-f]{24}$'},
                           'expected_sha256': {'type': 'string', 'pattern': '^(sha256:)?[0-9a-f]{64}$'},
                           'source_context': {'type': 'object'}, 'source_subject': {'type': 'object'},
                           'request_id': string, 'work_id': string, 'expected_work_revision': string, 'repository': string, 'parent_session_id': string,
                           'session_id': string, 'cut': string, 'part': {'enum': list(STATUS_PARTS)}, 'row_id': string,
                           'paths': {'type': 'array', 'items': string, 'maxItems': 64}, 'operations': {'type': 'array', 'items': {'enum': list(OPERATIONS)}},
                           'checks': {'type': 'object', 'additionalProperties': profile, 'maxProperties': 8},
                           'lifetime_s': {'type': 'integer', 'minimum': 60, 'maximum': MAX_LIFETIME_S},
                           'delegates': {'type': 'array', 'items': string, 'maxItems': 16}, 'evaluator': string,
                           'native_allowance': allowance, 'grant_id': string, 'reason': string, 'path': string, 'candidate_id': string, 'name': string,
                           'files': {'type': 'array', 'maxItems': 32, 'items': file},
                           'include_text': {'type': 'boolean', 'default': True},
                           **project_work_continuity.source_fields(),
                           'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 64}},
            'allOf': [{'if': {'required': ['include_text']}, 'then': {'properties': {'action': {'const': 'read'}}}},
                      {'if': {'required': ['native_allowance']}, 'then': {'properties': {'action': {'const': 'grant'}}}}],
            'description': 'grant (human/admin door only, POST /work/development; a native turn is refused): work_id, expected_work_revision, request_id, repository, '
                           'parent_session_id, evaluator, paths, operations[, checks, lifetime_s, delegates, native_allowance]; delegate (parent session: grant_id, session_id[, operations, paths], narrowing); '
                           'revoke (grant_id); read (grant_id, path[, include_text:false for pin/navigation only]; repository_read supplies existing pinned paging); candidate (grant_id, files: each path/before_sha256 and exactly one content or unique nonoverlapping original-text edits[{old,new}]); '
                           'lane (human door: work_id, expected_work_revision, parent_session_id[, lifetime_s]) cuts a lean worktree of the serving checkout and grants it to the parent session with the fixed check profiles; '
                           'discard (human door: work_id, branch) revokes the lane grants and removes the worktree; check targets[] name files matching the profile targets globs; '
                           'check profiles optionally fix exact evaluator bytes with fixed_inputs{path:sha256}, declare exact read-only dependencies{path:sha256} outside the writable paths and select runtime system|registered-python (executable "python"); apply (candidate_id); check (grant_id, name[, candidate_id]); status (work_id[, cut, offset, limit]; a NOT_EXPANDED row detail_read adds part, row_id, expected_sha256); '
                           'arm (the ACTIVE attached producer turn only: grant_id, candidate_id, request_id, expected_work_revision, obligation_id, recipient_binding_id, '
                           'pins (all cumulative required inputs), proof_slots [{id,label}], return_policy {review_deadline_s, max_attempts, parent_return|null}); '
                           'proof (intent_id, slot_id, reference {id|path+scope, expected_sha256}: arrival only, never acceptance).'}


def source_contract() -> dict:
    """This owner's source contract (laplace.work.source_contracts): admission, operations, budgets and authority as
    declared here, and their explicit consumers."""
    from laplace.work import source_contracts
    here = 'src/laplace/work/development_source.py'
    return source_contracts.validate(source_contracts.detached({
        'schema': source_contracts.SCHEMA, 'owner': 'domain.work', 'operation': 'development_source',
        'purpose': {'text': 'A configured repository becomes writable code under one human-issued Work grant: exact reads, a durable '
                            'recoverable apply and a budgeted isolated check.', 'assumptions': ['A native turn never issues a root grant.'],
                    'authored_by': 'development_source module text (J-R1..J-R3)'},
        'segments': {'admission': contract(), 'operations': {'operations': list(OPERATIONS), 'kinds': KINDS},
                     'budgets': {'lifetime_s': MAX_LIFETIME_S, 'candidate_bytes': MAX_CANDIDATE_BYTES, 'wall_s': MAX_CHECK_WALL_S,
                                 'compact_edits_per_file': MAX_COMPACT_EDITS,
                                 'output': MAX_CHECK_OUTPUT, 'memory': MAX_CHECK_MEMORY, 'processes': MAX_CHECK_PROCESSES,
                                 'scratch': [SCRATCH_MIN, SCRATCH_MAX], 'runtime_mount': str(RUNTIME_MOUNT)},
                     'review_basis': {'schema_version': REVIEW_BASIS_SCHEMA,
                         'prepare': prepare_review_basis.__module__ + '.' + prepare_review_basis.__name__,
                         'validate': validate_review_basis.__module__ + '.' + validate_review_basis.__name__,
                         'recipient': validate_review_recipient.__module__ + '.' + validate_review_recipient.__name__,
                         'prepare_plan': prepare_review_plan.__module__ + '.' + prepare_review_plan.__name__,
                         'project_plan': review_plan_for_inputs.__module__ + '.' + review_plan_for_inputs.__name__,
                         'plan_consumers': {'prepare': 'project_work_review._phase_row',
                             'project': ['work_delivery._revalidate', 'work_delivery._request_text']},
                         'context_windows': {'max': MAX_REVIEW_WINDOWS, 'units': 'inclusive1-based pinned postimage lines'},
                         'geometry_input_bytes': MAX_CANDIDATE_BYTES, 'read_page_chars': REVIEW_PAGE_CHARS,
                         'verified_edits_schema': VERIFIED_EDITS_SCHEMA, 'plan_schema': REVIEW_PLAN_SCHEMA,
                         'plan_schemas': list(REVIEW_PLAN_SCHEMAS), 'subject_schema': REVIEW_SUBJECT_SCHEMA, 'carry_schema': REVIEW_CARRY_SCHEMA,
                         'subject': review_subject.__module__ + '.' + review_subject.__name__,
                         'validate_subject': validate_review_subject.__module__ + '.' + validate_review_subject.__name__,
                         'subject_meaning': ('Whole cumulative review subject: every committed effect of the commission across reissued grants, '
                             'geometry derived from each retained raw preimage to the current postimage, an explicitly admitted read-only '
                             'carry manifest and a typed stage. The latest candidate/effect is the exact anchor and latest delta only.'),
                         'meaning': 'Current holder admission and committed candidate effect at handoff; recorded configured source identity and exact consumed pins for historical review, independent of expired write authority.'},
                     'execution_allowance': {'policy': contract()['properties']['native_allowance'],
                         'owner': 'laplace.writing.source_execution', 'attachment': 'laplace.source-execution/1',
                         'unit': 'one admitted native incoming dispatch, including later validation/refusal; no raw/token/currency ceiling',
                         'custody': 'existing Writing journal/index under existing Work admission lock',
                         'identity': 'actual project + Work + author commission_request_id; reissue does not reset',
                         'admission_consumer': 'turn_admission.admit', 'delivery_consumer': 'work_delivery.source_admission',
                         'limits': 'active effects may drain until finite wall; unresolved Python effects remain spent/unknown, not rolled back'},
                     'authority': {'grant': 'human/admin door only (POST /work/development)', 'protected': ['serving checkout', 'Main root', 'author drafts']}},
        'relations': [{'consumer': 'kernel.declared-source', 'relation': 'projects', 'segments': ['admission','operations','budgets','review_basis','execution_allowance','authority'], 'location': 'src/laplace/engine/source_kernel_input.py'},
                      {'consumer': 'writing.source_execution', 'relation': 'implements', 'segments': ['execution_allowance','authority'], 'location': 'src/laplace/writing/source_execution.py'},
                      {'consumer': 'writing.source_execution_admission', 'relation': 'consumes', 'segments': ['execution_allowance'], 'location': 'src/laplace/writing/turn_admission.py'},
                      {'consumer': 'native.source_execution', 'relation': 'consumes', 'segments': ['execution_allowance'], 'location': 'src/laplace/native/tools.py'},
                      {'consumer': 'work.work_delivery.source_execution', 'relation': 'consumes', 'segments': ['execution_allowance'], 'location': 'src/laplace/work/work_delivery.py'},
                      {'consumer': 'writing.source_execution_supervision', 'relation': 'consumes', 'segments': ['execution_allowance'], 'location': 'src/laplace/writing/turn_execution.py'},
                      {'consumer': 'tests.source_native_allowance', 'relation': 'evaluates', 'segments': ['execution_allowance','authority'], 'location': 'tests/test_source_native_allowance.py'},
                      {'consumer': 'work.development_source.grant', 'relation': 'implements', 'segments': ['admission', 'authority'], 'location': here},
                      {'consumer': 'work.development_source.apply', 'relation': 'implements', 'segments': ['operations'], 'location': here},
                      {'consumer': 'work.development_source.check', 'relation': 'implements', 'segments': ['budgets'], 'location': here},
                      {'consumer': 'work.development_source.review_basis', 'relation': 'implements', 'segments': ['review_basis', 'authority'], 'location': here},
                      {'consumer': 'work.work_review.qualified_source_basis', 'relation': 'consumes', 'segments': ['review_basis', 'authority'],
                       'location': 'src/laplace/work/project_work_review.py'},
                      {'consumer': 'work.work_delivery.qualified_source_basis', 'relation': 'consumes', 'segments': ['review_basis', 'authority'],
                       'location': 'src/laplace/work/work_delivery.py'},
                      {'consumer': 'work.work_review.source_review_plan', 'relation': 'consumes', 'segments': ['review_basis', 'admission'], 'location': 'src/laplace/work/project_work_review.py'},
                      {'consumer': 'work.work_delivery.source_review_plan', 'relation': 'consumes', 'segments': ['review_basis'], 'location': 'src/laplace/work/work_delivery.py'},
                      {'consumer': 'tests.source_review_plan', 'relation': 'evaluates', 'segments': ['review_basis', 'admission'], 'location': 'tests/test_source_review_plan.py'},
                      {'consumer': 'tests.source_use_joins', 'relation': 'evaluates', 'segments': ['admission', 'operations', 'budgets', 'review_basis', 'authority'],
                       'location': 'tests/test_source_use_joins.py'},
                      {'consumer': 'native.development_source', 'relation': 'projects', 'segments': ['admission'], 'location': 'src/laplace/native/declared.py'},
                      {'consumer': 'tests.development_source_recipient', 'relation': 'evaluates', 'segments': ['admission', 'operations', 'budgets', 'authority'],
                       'location': 'tests/test_development_source_recipient.py'}],
        'steps': [{'id': name, 'object': 'grant' if name == 'read' else 'configured checkout'} for name in OPERATIONS],
        'authority': {'grant': 'human/admin only'}, 'recovery': 'apply: one durable transaction per candidate; the same candidate recovers.'}))


REQUIRED = {'grant': ('request_id', 'work_id', 'expected_work_revision', 'repository', 'parent_session_id', 'evaluator', 'paths', 'operations'),
            'lane': ('work_id', 'expected_work_revision', 'parent_session_id'), 'discard': ('work_id', 'branch'),
            'delegate': ('grant_id', 'session_id'), 'revoke': ('grant_id',),
            'read': ('grant_id', 'path'), 'candidate': ('grant_id', 'files'), 'apply': ('candidate_id',), 'check': ('grant_id', 'name'), 'status': ('work_id',)}


def _require(payload: dict, action: str) -> None:
    if 'include_text' in payload:
        if action != 'read':
            raise ValueError('development_source: include_text is a read-only projection option.')
        if not isinstance(payload['include_text'], bool):
            raise ValueError('development_source: include_text must be a boolean.')
    missing = [key for key in REQUIRED[action] if payload.get(key) in (None, '', [], {})]
    if missing:
        raise ValueError('development_source %s requires %s.' % (action, ', '.join(missing)))


# ------------------------------------------------------------------------------------------------ the ledger view

def rows(task: dict, kind: str) -> list[dict]:
    key = KINDS[kind]
    return [row for row in task.get('development') or () if row.get('kind') == key]


def _latest(task: dict, kind: str, ident: str) -> dict | None:
    found = None
    for row in rows(task, kind):
        if row.get('id') == ident:
            found = row
    return found


def cut(task: dict, root) -> str:
    """The local owner cut of the development view: the identity of every attached row (id, state, ts) in ledger order and
    the CANONICAL Work basis the grants are bound to (project_work._work_basis, read with the same root as the page). Any
    append, update or goal/scope change moves it, so a continuation naming an old cut is refused, never mixed (J-R5-R1)."""
    from laplace.work import project_work
    basis, issue = project_work._work_basis(project_work._tasks(task['project'], root), task['id'])
    return _digest({'rows': [(row.get('id'), row.get('state'), row.get('ts') or row.get('granted_at')) for row in task.get('development') or ()],
                    'basis': {'revision': basis.get('revision'), 'scope_revision': basis.get('scope_revision'), 'issue': issue}})


#: The Work detail embeds its development facet as a fitted page of at most this many encoded bytes (status continues
#: it); a status row that alone exceeds a line is paged by its detail_read in pages of this escaped size. No cap is raised.
FACET_INLINE_BYTES = 16000
ROW_PAGE_JSON_BYTES = 12000
ROW_SCHEMA = 'laplace.development-status-row/1'
STATUS_PAGE_MEANING = ('Every part pages from the same offset. A page holding fewer rows than requested_limit, or a row with '
                       'expanded:false, omits nothing: next_read continues at the next row and detail_read pages the exact whole row. '
                       'The whole encoded response fits the delivery line.')


def _status_items(task: dict) -> dict:
    """Every retained row of each part, newest first (the latest state of each identity): the exact identities a complete
    traversal of the status pages covers, each once."""
    grants = [{key: row.get(key) for key in ('id', 'state', 'repository', 'base', 'paths', 'operations', 'expires_at', 'evaluator', 'parent_session_id', 'delegates')}
              | {'checks': sorted((row.get('checks') or {}).keys()), 'grantor': (row.get('actor') or {}).get('actor')} for row in _latest_per_id(rows(task, 'grant'))]
    candidates = [{'id': row['id'], 'grant_id': row['grant_id'], 'files': [f['path'] for f in row['files']], 'bytes': row['bytes']}
                  for row in _latest_per_id(rows(task, 'candidate'))]
    effects = [{key: row.get(key) for key in ('id', 'candidate_id', 'grant_id', 'state', 'ts')} | {'files': [(f['path'], f['state']) for f in row.get('files') or []]}
               for row in _latest_per_id(rows(task, 'effect'))]
    checks = [{key: row.get(key) for key in ('id', 'grant_id', 'name', 'state', 'exit_code', 'wall_ms', 'stdout_bytes', 'truncated', 'retained_bytes', 'ts')}
              | {key: row[key] for key in ('targets', 'failing', 'failing_total', 'failing_complete', 'sandbox_differences') if key in row}
              | {'scratch_bytes': (row.get('budgets') or {}).get('scratch_bytes'),
                 # recorded stage disposition (no recorded outcome is UNKNOWN; observing it cleans nothing)
                 'stage_cleanup': (row.get('stage_cleanup') or {}).get('state') or 'UNKNOWN'}
              | ({'output_read': output_handle(task['project'], task['id'], row['id'], row['stdout_sha256'])}
                 if row.get('stdout_sha256') and row.get('id') else {})
              for row in _latest_per_id(rows(task, 'check'))]
    return {'grants': grants[::-1], 'candidates': candidates[::-1], 'effects': effects[::-1], 'checks': checks[::-1]}


def _encoded(value) -> int:
    """The largest encoding any door emits for value: the native model text and both JSON spellings (UTF-8 and escaped)."""
    from laplace.writing import delivery
    return max(delivery.emitted(value), len(json.dumps(value).encode('utf-8')), len(json.dumps(value, ensure_ascii=False).encode('utf-8')))


def _row_text(row) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _row_sha(row) -> str:
    return 'sha256:' + hashlib.sha256(_row_text(row).encode('utf-8')).hexdigest()


def row_handle(project, work_id, part, row_id, row_sha256, offset=0) -> dict:
    """The ONE exact paged read of a whole status row (canonical JSON), pinned to its row_sha256."""
    payload = {'action': 'status', 'work_id': work_id, 'part': part, 'row_id': row_id, 'expected_sha256': row_sha256, 'offset': offset}
    return {'operation': 'development_source', 'payload': payload,
            'http': {'method': 'POST', 'url': '/work/development', 'payload': {'project': project, **payload}}}


def _row_header(task, part, row) -> dict:
    digest = _row_sha(row)
    return {'id': row.get('id'), **({'state': row['state']} if 'state' in row else {}), 'expanded': False, 'row_sha256': digest,
            'row_chars': len(_row_text(row)),
            'counts': {key: len(value) for key, value in sorted(row.items()) if isinstance(value, (list, tuple, dict))},
            'detail_read': row_handle(task['project'], task['id'], part, row.get('id'), digest)}


def _fitted(task, root, offset, requested, line, wrap) -> tuple:
    """(result, fit): the largest page of at most `requested` rows per part, every part from the same offset, whose WHOLE
    encoded wrap(development) fits `line`. At one row, a row that alone exceeds the line becomes a NOT_EXPANDED header
    (largest first) with its exact detail_read. Nothing is clipped, hidden or capped: next_read continues at offset + the
    delivered rows with the requested limit, pinned to the cut."""
    pinned = cut(task, root)
    items = _status_items(task)

    def build(limit, compact=frozenset()):
        def page(part):
            listed = items[part]
            selected = [_row_header(task, part, row) if (part, row.get('id')) in compact else row for row in listed[offset:offset + limit]]
            more = offset + limit < len(listed)
            return {'total': len(listed), 'offset': offset, 'limit': limit, 'requested_limit': requested, 'items': selected, 'cut': pinned,
                    'next_read': {'operation': 'development_source', 'payload': {'action': 'status', 'work_id': task['id'],
                                  'offset': offset + limit, 'limit': requested, 'cut': pinned}} if more else None}
        return wrap({'cut': pinned, **{part: page(part) for part in STATUS_PARTS}})

    def fits(value):
        return line is None or _encoded(value) <= line
    limit, result = requested, build(requested)
    if not fits(result):
        low, high = 1, requested - 1
        while low < high:
            middle = (low + high + 1) // 2
            if fits(build(middle)):
                low = middle
            else:
                high = middle - 1
        limit = low
        result = build(limit)
    compact = set()
    if not fits(result):
        for _size, part, ident in sorted(((_encoded(row), part, row.get('id')) for part in STATUS_PARTS
                                          for row in items[part][offset:offset + limit]), reverse=True):
            compact.add((part, ident))
            result = build(limit, frozenset(compact))
            if fits(result):
                break
    return result, {'offset': offset, 'limit': limit, 'requested_limit': requested, 'not_expanded': sorted([list(key) for key in compact])}


def facet(task: dict, root, *, offset: int = 0, limit: int = PAGE, line: int | None = FACET_INLINE_BYTES) -> dict | None:
    """The Work detail's development facet: owner-pinned counts and one bounded page of the latest rows of each kind,
    no bodies; the next page is one exact read (development_source status) pinned to this view's cut. The embedded facet
    is itself a fitted page (_fitted, at most FACET_INLINE_BYTES encoded)."""
    if not task.get('development'):
        return None
    return _fitted(task, root, offset, limit, line, lambda development: development)[0]


def row_detail(root: Path, project: str, payload: dict, door: dict) -> dict:
    """ONE page of the exact canonical JSON of one status row (the detail_read of its NOT_EXPANDED header), pinned to
    row_sha256 and fitted to the delivery line in Unicode characters. A changed row or an offset past its end refuses
    with the exact restart of the same row; an unknown row discloses nothing. Reading executes and records nothing."""
    from laplace.work import project_work
    from laplace.work import project_work_navigation as nav
    from laplace.writing import delivery
    _require(payload, 'status')
    task = project_work._tasks(project, root).get(payload['work_id'])
    part, ident = payload.get('part'), payload.get('row_id')
    row = None
    if task is not None and part in STATUS_PARTS:
        row = next((item for item in _status_items(task)[part] if item.get('id') == ident), None)
    if row is None:
        raise ValueError('development_source: no status row with these identities is recorded on a Work of this project (unknown '
                         'or foreign); nothing is disclosed and no read is issued.')
    text, digest = _row_text(row), _row_sha(row)
    restart = row_handle(project, task['id'], part, ident, digest)
    pin = str(payload.get('expected_sha256') or '')
    if 'sha256:' + pin.removeprefix('sha256:') != digest:
        raise _view_refusal('development_source: status row %s changed since its header was issued; restart_read reads its current '
                            'whole row from the start.' % ident, project, task['id'], code='STALE_PIN', field='expected_sha256',
                            expected=pin or None, observed=digest, restart=restart)
    offset = int(payload.get('offset') or 0)
    if offset > len(text):
        raise _view_refusal('development_source: offset %d is beyond the %d characters of status row %s.' % (offset, len(text), ident),
                            project, task['id'], code='PAST_END', field='offset', expected=len(text), observed=offset, restart=restart)
    line = delivery.owner_line()
    line = nav.CAP if line is None else line

    def page(end):
        return {'schema_version': ROW_SCHEMA, 'work_id': task['id'], 'part': part, 'row_id': ident, 'row_sha256': digest,
                'units': 'Unicode characters of the canonical JSON row (sorted keys, compact separators, UTF-8)', 'chars': len(text),
                'offset': offset, 'end_offset': end, 'content': text[offset:end], 'eof': end == len(text),
                'page_read': row_handle(project, task['id'], part, ident, digest, offset),
                'next_read': row_handle(project, task['id'], part, ident, digest, end) if end < len(text) else None,
                'restart_read': restart, 'authority': 'The exact recorded status row; reading it executes, renews and records nothing.'}
    end = min(len(text), offset + ROW_PAGE_JSON_BYTES)
    while end - offset > 1 and len(json.dumps(text[offset:end]).encode('utf-8')) > ROW_PAGE_JSON_BYTES:
        end = offset + max(1, (end - offset) * 3 // 4)
    value = page(end)
    while end - offset > 1 and _encoded(value) > line:
        end = offset + max(1, (end - offset) * 3 // 4)
        value = page(end)
    delivery.record_projection('row', {'part': part, 'row_id': ident, 'offset': offset, 'end_offset': end})
    return value


def _view_refusal(message, project, work_id, *, code, field, expected=None, observed=None, restart=None, reinspect=None, **facts):
    """A STRUCTURED scoped refusal of a status view: typed details travel through the native and HTTP doors (never JSON in
    the text). A lawful same-record restart is restart_read and the first next read; UNAVAILABLE issues none."""
    from laplace.work import project_work
    refusal = project_work.WorkConflict(message, project, work_id, expected=expected, observed=observed, field=field)
    refusal.details.update(code=code, restart_read=restart, next_reads=[read for read in (restart, reinspect) if read], **facts)
    return refusal


def _latest_per_id(items):
    latest = {}
    for row in items:
        latest[row['id']] = row
    return list(latest.values())


# ------------------------------------------------------------------------------------------------ identity

def _acting(root, project, door) -> dict:
    """What the door proved: {'kind': 'human'} or {'kind': 'native', 'session_id', 'turn_id', 'role'}."""
    if door.get('origin') != 'native':
        return {'kind': 'human'}
    from laplace.writing import records as writing_records
    fold = writing_records.fold_records(root)
    turn = fold['turns'].get(door.get('turn_id')) or {}
    if not turn or turn.get('project') != project:
        raise ValueError('development_source: the acting turn is not an admitted turn of this project.')
    session = fold['sessions'].get(turn.get('session_id')) or {}
    role = 'review' if (turn.get('mode') == 'review' or session.get('role') == 'review') else 'author'
    return {'kind': 'native', 'session_id': turn.get('session_id'), 'turn_id': turn['id'], 'role': role,
            'dispatch_id': turn.get('dispatch_id'), 'parent_turn_id': turn.get('parent_turn_id')}


def _actor(root, project, payload, door) -> dict:
    from laplace.work import project_work_review
    actor = project_work_review._actor(root, project, {k: v for k, v in payload.items() if k in ('actor',)} | {'phase': 'handoff'}, door)
    if door.get('origin') == 'native':
        from laplace.writing import delivery
        invocation=delivery._invocation();holder=invocation.get('native') if invocation else None
        if holder and holder.source_admitted and holder.source_scope and holder.source_scope[2]==door.get('turn_id'):
            actor={**actor,'source_execution':{'commission_id':holder.source_attachment['commission_id'],
                'allowance_revision':holder.source_attachment['allowance_revision'],
                'native_invocation_id':holder.native_invocation_id,'claim_id':holder.source_claim}}
    return actor


def _protected_roots(root: Path) -> list[Path]:
    from laplace.core import checkout as serving
    return [serving.repo_root().resolve(), MAIN_ROOT.resolve(), (Path(root) / 'writing_projects').resolve()]


def _checkout(root: Path, repository: str) -> Path:
    from laplace.projects import writing_sources
    declared, _config = writing_sources._declared(root)
    for name, path in declared:
        if name == repository:
            return path.resolve()
    raise ValueError('development_source: choose a repository configured for this project (repository {action:"list"}).')


def lane_home() -> Path:
    """Where lanes are cut: LANE_HOME, or the directory a test or scenario names in LAPLACE_DEV_LANE_HOME."""
    return Path(os.environ.get(LANE_HOME_ENV) or LANE_HOME).expanduser().resolve()


def lane_row(task: dict | None) -> dict | None:
    """The latest development-lane row of this Work (its one lane identity lane:<work-id>), or None."""
    return _latest(task, 'lane', LANE_PREFIX + str(task['id'])) if task else None


def basis_checkout(root: Path, project: str, work_id: str, repository: str, purpose: str) -> Path:
    """THE ONE RESOLVER of a development basis (incorporation D4): grant, every operation, review currentness and the source
    kernel resolve a repository here. A registered repository resolves as configured (profiles/writing_sources.json). A
    lane:<work-id> id resolves only from the latest lane row of that same Work: ACTIVE gives the lane checkout; ADOPTED gives
    the serving checkout for read-only currentness (purpose 'currentness') and nothing else; DISCARDED is UNKNOWN (a
    ValueError the caller reports). The protected-root refusal stays with the caller (grant, apply and check keep it).
    The serving checkout here is the app's own source tree (laplace.core.checkout.source_tree), whose HEAD a lane is cut from."""
    if not str(repository).startswith(LANE_PREFIX):
        return _checkout(root, repository)
    if repository != LANE_PREFIX + str(work_id):
        raise ValueError('development_source: %s is the lane of another Work; a lane is resolved only for its own Work %s.' % (repository, work_id))
    from laplace.work import project_work
    row = lane_row(project_work._tasks(project, root).get(work_id))
    if row is None:
        raise ValueError('development_source: no lane has been cut for Work %s (action lane).' % work_id)
    if row['state'] == 'ACTIVE':
        return Path(row['checkout']).resolve()
    if row['state'] == 'ADOPTED' and purpose == 'currentness':
        from laplace.core import checkout as serving
        return serving.source_tree().resolve()
    if row['state'] == 'ADOPTED':
        raise ValueError('development_source: lane %s was adopted; it is read for currentness only and grants nothing.' % repository)
    raise ValueError('development_source: lane %s is %s; its bytes exist only in history (UNKNOWN).' % (repository, row['state']))


def _refuse_protected(root: Path, checkout: Path) -> None:
    for protected in _protected_roots(root):
        if checkout == protected or checkout.is_relative_to(protected) or protected.is_relative_to(checkout):
            raise ValueError('development_source: the serving checkout, the canonical Main root and author drafts are never a development resource, '
                             'as the checkout or inside it; configure a separate checkout.')


def _refuse_checkout(root: Path, checkout: Path) -> None:
    _refuse_protected(root, checkout)
    if not checkout.is_dir():
        raise ValueError('development_source: the configured checkout is not present on this machine.')


def _base(checkout: Path) -> str:
    from laplace.core import versioning as gitio
    sha = gitio.head_sha(checkout)
    if not sha:
        raise ValueError('development_source: the checkout is not a git repository with a base commit.')
    return sha


def _evaluator_binding(task: dict, binding_id: str | None) -> dict | None:
    if not binding_id:
        return None
    from laplace.work import work_delivery
    binding = work_delivery._latest(task, work_delivery.BINDING, binding_id)
    if binding is None or binding.get('state') != 'APPROVED' or binding.get('role') != 'review':
        raise ValueError('development_source: evaluator names an approved review binding of this Work (work_delivery bind).')
    return binding


# ------------------------------------------------------------------------------------------------ the grant

def _author_session(root: Path, project: str, session_id: str, what: str) -> dict:
    from laplace.writing import records as writing_records
    session = writing_records.fold_records(root)['sessions'].get(session_id) or {}
    if not session or session.get('project') != project:
        raise ValueError('development_source: %s names an existing session of this project.' % what)
    if session.get('role', 'author') != 'author':
        raise ValueError('development_source: %s is an author-role session; a review session holds no source authority.' % what)
    return session


def grant(root: Path, project: str, payload: dict, door: dict) -> dict:
    """The ROOT grant: issued only through the human/admin owner boundary to an exact parent session (Root decision
    BOOTSTRAP). A native turn, whatever its mode, is refused here: it neither issues nor reissues root authority."""
    _require(payload, 'grant')
    return _issue(root, project, payload, door)


def _issue(root: Path, project: str, payload: dict, door: dict) -> dict:
    """The issuing body shared by grant and lane: a lane grant carries no evaluator (its REQUIRED omits it)."""
    from laplace.work import project_work
    if door.get('origin') != 'human':
        raise ValueError('development_source: root source authority is issued only through the human/admin owner boundary (POST /work/development) '
                         'to an exact parent session; a native turn cannot issue or reissue it. The authorised parent session narrows its own grant '
                         'to a child with action delegate.')
    request = str(payload['request_id'])
    if not (8 <= len(request) <= 96):
        raise ValueError('development_source: request_id is a stable client id of 8-96 characters.')
    from laplace.writing import source_execution
    native_allowance = source_execution.validate_policy(payload['native_allowance']) if 'native_allowance' in payload else None
    checkout = basis_checkout(root, project, payload['work_id'], payload['repository'], 'grant')
    _refuse_checkout(root, checkout)
    base = _base(checkout)
    for pattern in payload['paths']:
        if pattern.startswith('/') or '..' in Path(pattern).parts or pattern.startswith('.git'):
            raise ValueError('development_source: permitted paths are checkout-relative globs without .. or .git.')
    checks = payload.get('checks') or {}
    admissions, manifests = {}, {}
    for name, profile in checks.items():
        if profile.get('runtime', 'system') == REGISTERED_RUNTIME:
            if profile['executable'] != 'python':
                raise ValueError('development_source: a registered-python check names the role executable "python"; a host path is never runtime authority.')
            admissions[name] = registered_runtime(root)
        else:
            executable = Path(profile['executable'])
            if not executable.is_absolute() or not executable.resolve().is_relative_to(RUNTIME_MOUNT):
                raise ValueError('development_source: a check executable is an absolute path under the read-only runtime mount %s.' % RUNTIME_MOUNT)
        dependencies = profile.get('dependencies', {})
        _review_pins(dependencies, allow_empty=True)
        for path, pin in dependencies.items():
            if _pin(_dependency_path(root, checkout, payload['paths'], path)) != pin:
                raise ValueError('development_source: check %s dependency %s is missing or differs from its declared pin.' % (name, path))
        if profile.get('dependency_manifest') is not None:
            manifests[name] = resolve_dependency_manifest(root, project, checkout, payload['paths'], profile['dependency_manifest'], dependencies)
        for pattern in profile['inputs']:
            if not any(fnmatch.fnmatchcase(pattern, allowed) or pattern == allowed or fnmatch.fnmatchcase(allowed, pattern) for allowed in payload['paths']):
                raise ValueError('development_source: check %s input %s is outside the grant paths.' % (name, pattern))
        for pattern in profile.get('targets') or ():
            if not any(fnmatch.fnmatchcase(pattern, allowed) or pattern == allowed for allowed in profile['inputs']):
                raise ValueError('development_source: check %s target glob %s is outside its inputs.' % (name, pattern))
        if profile.get('requires_targets') and not profile.get('targets'):
            raise ValueError('development_source: check %s requires targets but declares no targets globs.' % name)
        fixed = profile.get('fixed_inputs', {})
        _review_pins(fixed, allow_empty=True)
        for path, pin in fixed.items():
            if not any(fnmatch.fnmatchcase(path, pattern) for pattern in profile['inputs']):
                raise ValueError('development_source: fixed input %s is outside check %s inputs.' % (path, name))
            target = _fenced(root, checkout, {'paths': payload['paths']}, path)
            if _pin(target) != pin:
                raise ValueError('development_source: fixed check input changed: ' + path)
    for name, profile in checks.items():
        scratch = int(profile.get('scratch_bytes') or SCRATCH_PAGE * 16)
        if scratch < SCRATCH_MIN or scratch > SCRATCH_MAX or scratch % SCRATCH_PAGE:
            raise ValueError('development_source: check %s scratch_bytes %d is unsupported: the scratch budget is in bytes, a whole multiple of the %d-byte page, '
                             'between %d and %d (every file consumes at least one page); it is refused, never rounded.' % (name, scratch, SCRATCH_PAGE, SCRATCH_MIN, SCRATCH_MAX))
    parent_session = str(payload['parent_session_id'])
    _author_session(root, project, parent_session, 'parent_session_id')
    operations = sorted(set(payload['operations']))
    delegates = {}
    for item in payload.get('delegates') or []:
        _author_session(root, project, str(item), 'delegate ' + str(item))
        delegates[str(item)] = {'operations': list(operations), 'paths': list(payload['paths'])}
    lifetime = int(payload.get('lifetime_s') or 3600)
    with project_work.dispatch_lock(root):
        tasks = project_work._tasks(project, root)
        task = tasks.get(payload['work_id'])
        if task is None:
            raise ValueError('development_source: name an existing Work id of this project.')
        if payload['expected_work_revision'] != project_work._task_revision(task):
            raise project_work.WorkConflict('Read the exact Work before granting development source.', project, task['id'],
                                            expected=payload['expected_work_revision'], observed=project_work._task_revision(task), field='expected_work_revision')
        basis, issue = project_work._work_basis(tasks, task['id'])
        if issue or not basis.get('scope_revision'):
            raise ValueError('development_source: the Work has no current material scope: ' + str(issue))
        evaluator = _evaluator_binding(task, payload.get('evaluator'))
        actor = _actor(root, project, payload, door)
        identity = {'work_id': task['id'], 'repository': payload['repository'], 'checkout': str(checkout), 'base': base,
                    'work_scope_revision': basis['scope_revision'], 'paths': sorted(payload['paths']), 'operations': operations,
                    'checks': sorted(checks), 'parent_session_id': parent_session, 'evaluator': evaluator['id'] if evaluator else None, 'request_id': request}
        if native_allowance is not None:
            for prior in rows(task, 'grant'):
                policy = prior.get('native_allowance')
                if policy and policy['commission_request_id'] == native_allowance['commission_request_id']:
                    if policy != native_allowance or prior['parent_session_id'] != parent_session:
                        raise ValueError('Source commission policy/original parent is immutable across grant reissue.')
            identity['native_allowance'] = native_allowance
        fixed = {name: dict(p['fixed_inputs']) for name, p in checks.items() if p.get('fixed_inputs')}
        if fixed:
            identity['fixed_check_inputs'] = fixed
        dependencies = {name: dict(p['dependencies']) for name, p in checks.items() if p.get('dependencies')}
        if dependencies:
            identity['check_dependencies'] = dependencies
        if admissions:
            identity['check_runtimes'] = {name: basis['identity'] for name, basis in admissions.items()}
        if manifests:
            identity['check_dependency_manifests'] = {name: closure['digest'] for name, closure in manifests.items()}
        ident = 'DG-' + _digest(identity)[7:31]
        existing = _latest(task, 'grant', ident)
        if existing is not None:   # a stable replay answers the existing grant: no new expiry, no new actor
            return {'ok': True, 'reused': True, 'grant': _public_grant(existing)}
        now = time.time()
        row = {'record': RECORD, 'kind': KINDS['grant'], 'id': ident, 'work_id': task['id'], 'project': project, 'state': 'ACTIVE',
               'repository': payload['repository'], 'checkout': str(checkout), 'base': base, 'work_scope_revision': basis['scope_revision'],
               'paths': list(payload['paths']), 'operations': operations,
               'checks': {name: {'executable': p['executable'], 'args': list(p['args']), 'inputs': list(p['inputs']),
                                 'timeout_s': int(p.get('timeout_s') or 60), 'max_output_bytes': int(p.get('max_output_bytes') or 65536),
                                 'scratch_bytes': int(p.get('scratch_bytes') or SCRATCH_PAGE * 16),
                                 'memory_bytes': int(p.get('memory_bytes') or 512 * 1024 ** 2), 'max_processes': int(p.get('max_processes') or 16),
                                 **({'fixed_inputs': dict(p['fixed_inputs'])} if 'fixed_inputs' in p else {}),
                                 **({'dependencies': dict(p['dependencies'])} if p.get('dependencies') else {}),
                                 **({'runtime': REGISTERED_RUNTIME, 'runtime_admission': admissions[name]} if name in admissions else {}),
                                 **({'dependency_manifest': manifests[name]} if name in manifests else {}),
                                 **({key: copy.deepcopy(p[key]) for key in ('targets', 'requires_targets', 'failures', 'sandbox_differences') if key in p})}
                          for name, p in checks.items()},
               'granted_at': _now(), 'ts': _now(), 'expires_at': dt.datetime.fromtimestamp(now + lifetime, dt.timezone.utc).isoformat(),
               'request_id': request, 'evaluator': evaluator['id'] if evaluator else None, 'evaluator_revision': evaluator['revision'] if evaluator else None,
               'parent_session_id': parent_session, 'delegates': delegates,
               **({'native_allowance': native_allowance} if native_allowance is not None else {}),
               'grantor': {'kind': 'human', 'door': 'human/admin', 'parent_session_id': parent_session}, 'actor': actor}
        project_work._append(root, row)
    return {'ok': True, 'grant': _public_grant(row), 'read': {'operation': 'project', 'payload': {'view': 'detail', 'id': task['id']}}}


def _public_grant(row: dict) -> dict:
    return copy.deepcopy({key: row.get(key) for key in ('id', 'state', 'work_id', 'repository', 'base', 'work_scope_revision', 'paths', 'operations', 'checks',
                                          'expires_at', 'evaluator', 'parent_session_id', 'delegates', 'grantor', 'request_id')} |
                         ({'native_allowance': row['native_allowance']} if 'native_allowance' in row else {}))


def _parent_or_human(acting: dict, row: dict, what: str) -> None:
    if acting['kind'] == 'native' and (acting.get('role') == 'review' or acting.get('session_id') != row.get('parent_session_id')):
        raise ValueError('development_source: only the author/admin door or the authorised parent session %s a grant.' % what)


def delegate(root: Path, project: str, payload: dict, door: dict) -> dict:
    """The authorised parent session (or the human door) narrows its own root grant to an actual child session: a subset of
    the grant's operations and paths, under the same grant row. Nothing is widened, nothing is issued."""
    from laplace.work import project_work
    _require(payload, 'delegate')
    acting = _acting(root, project, door)
    with project_work.dispatch_lock(root):
        task, row = _find_grant(root, project, payload['grant_id'])
        _parent_or_human(acting, row, 'delegates')
        if acting['kind']=='native' and row.get('native_allowance'):
            from laplace.writing import source_execution
            source_execution.require_grant(root, project, row, acting['turn_id'])
        if row['state'] != 'ACTIVE':
            raise GrantRefused(row['id'], ['grant is ' + row['state']])
        child = str(payload['session_id'])
        if child == row.get('parent_session_id'):
            raise ValueError('development_source: the parent session already holds the grant; delegate names a child session.')
        _author_session(root, project, child, 'delegate session_id')
        operations = sorted(set(payload.get('operations') or row['operations']))
        paths = list(payload.get('paths') or row['paths'])
        if not set(operations) <= set(row['operations']) or not set(paths) <= set(row['paths']):
            raise ValueError('development_source: a delegation only narrows: operations %s and paths %s must be within the grant\'s %s / %s.'
                             % (operations, paths, row['operations'], row['paths']))
        delegates = dict(row.get('delegates') or {})
        if delegates.get(child) == {'operations': operations, 'paths': paths}:
            return {'ok': True, 'reused': True, 'grant': _public_grant(row)}
        delegates[child] = {'operations': operations, 'paths': paths}
        updated = {**row, 'delegates': delegates, 'ts': _now(), 'delegated_by': _actor(root, project, payload, door)}
        project_work._append(root, updated)
    return {'ok': True, 'grant': _public_grant(updated)}


def revoke(root: Path, project: str, payload: dict, door: dict) -> dict:
    from laplace.work import project_work
    _require(payload, 'revoke')
    acting = _acting(root, project, door)
    with project_work.dispatch_lock(root):
        task, row = _find_grant(root, project, payload['grant_id'])
        _parent_or_human(acting, row, 'withdraws')
        if acting['kind']=='native' and row.get('native_allowance'):
            from laplace.writing import source_execution
            source_execution.require_grant(root, project, row, acting['turn_id'])
        if row['state'] != 'ACTIVE':
            return {'ok': True, 'grant': _public_grant(row), 'already': row['state']}
        withdrawn = {**row, 'state': 'REVOKED', 'revoked_at': _now(), 'reason': str(payload.get('reason') or '')[:400],
                     'revoked_by': _actor(root, project, payload, door)}
        project_work._append(root, withdrawn)
    return {'ok': True, 'grant': _public_grant(withdrawn)}


def _find_grant(root, project, grant_id) -> tuple[dict, dict]:
    from laplace.work import project_work
    for task in project_work._tasks(project, root).values():
        row = _latest(task, 'grant', grant_id)
        if row is not None:
            return task, row
    raise ValueError('development_source: unknown grant %s for this project.' % grant_id)


class GrantRefused(ValueError):
    def __init__(self, grant_id, problems):
        self.grant_id, self.problems = grant_id, list(problems)
        super().__init__('development_source grant %s refused: %s' % (grant_id, '; '.join(problems)))


def _reviewer_sessions(task: dict, evaluator: str | None) -> set:
    """The reviewer sessions an ADMITTED delivery to the evaluator binding opened: the scoped-reading identities."""
    if not evaluator:
        return set()
    from laplace.work import work_delivery
    return {row.get('session_id') for row in work_delivery._rows(task, work_delivery.EVENT)
            if row.get('state') in ('RESERVED', 'DELIVERED', 'ADMITTED') and (row.get('recipient') or {}).get('id') == evaluator and row.get('session_id')}


def _current(root: Path, project: str, grant_id: str, operation: str, door: dict) -> tuple[dict, dict, Path]:
    """The grant as it stands NOW, for this operation and this identity: every refusal here, before any read or effect."""
    from laplace.work import project_work
    task, row = _find_grant(root, project, grant_id)
    problems = []
    if row['state'] != 'ACTIVE':
        problems.append('grant is ' + row['state'])
    if dt.datetime.fromisoformat(row['expires_at']) <= dt.datetime.now(dt.timezone.utc):
        problems.append('grant lifetime expired at ' + row['expires_at'])
    if operation not in row['operations']:
        problems.append('operation %s is not in the grant' % operation)
    tasks = project_work._tasks(project, root)
    basis, issue = project_work._work_basis(tasks, task['id'])
    if issue or basis.get('scope_revision') != row['work_scope_revision']:
        problems.append('the Work material scope changed since the grant (%s -> %s)' % (row['work_scope_revision'], basis.get('scope_revision')))
    checkout = Path(row['checkout'])
    try:
        resolved = basis_checkout(root, project, task['id'], row['repository'], 'operation')
        if resolved != checkout:
            problems.append('the configured resource %s now resolves to %s, not the granted checkout' % (row['repository'], resolved))
        _refuse_checkout(root, checkout)
    except ValueError as exc:
        problems.append(str(exc))
    try:
        base = _base(checkout)
        if base != row['base']:
            problems.append('the checkout base moved (%s -> %s)' % (row['base'][:12], base[:12]))
    except ValueError as exc:
        problems.append(str(exc))
    if row.get('evaluator'):
        try:
            binding = _evaluator_binding(task, row['evaluator'])
            if binding and binding.get('revision') != row.get('evaluator_revision'):
                problems.append('the evaluator binding changed')
        except ValueError as exc:
            problems.append(str(exc))
    acting = _acting(root, project, door)
    effective = row
    if acting['kind'] == 'native' and row.get('native_allowance'):
        from laplace.writing import source_execution
        source_execution.require_grant(root, project, row, acting['turn_id'])
    if acting['kind'] == 'native':
        session = acting.get('session_id')
        if acting.get('role') == 'review':
            if operation != 'read' or session not in _reviewer_sessions(task, row.get('evaluator')):
                problems.append('a review-role turn reads only, and only as the admitted evaluator session of this Work')
        elif session == row.get('parent_session_id'):
            pass
        elif session in (row.get('delegates') or {}):
            subset = row['delegates'][session]
            if operation not in subset['operations']:
                problems.append('operation %s is outside the subset delegated to session %s' % (operation, session))
            effective = {**row, 'paths': list(subset['paths']), 'operations': list(subset['operations'])}
        else:
            problems.append('session %s is neither the authorised parent session nor a delegate of this grant' % session)
    if problems:
        raise GrantRefused(grant_id, problems)
    return task, effective, checkout


def execution_attachment(root: Path, project: str, grant_id: str, parent_session_id: str) -> dict:
    """Resolve only a human-issued opted-in grant for its already existing original parent."""
    from laplace.writing import source_execution
    _task, row = _find_grant(root, project, grant_id)
    if not row.get('native_allowance') or row['parent_session_id'] != parent_session_id:
        raise ValueError('Source selector must name the opted-in grant of this exact original parent session.')
    _author_session(root, project, parent_session_id, 'Source original parent')
    _current(root, project, grant_id, row['operations'][0], {'origin': 'human'})
    return source_execution.descriptor(project, row['work_id'], row['id'], parent_session_id, row['native_allowance'])


# ------------------------------------------------------------------------------------------------ fenced paths

def _fenced(root: Path, checkout: Path, grant_row: dict, raw: str) -> Path:
    """One permitted file inside the checkout and outside every protected root: no escape, no symlink component, no .git or
    credential-shaped name, a permitted glob."""
    relative = Path(str(raw))
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise ValueError('development_source: paths are checkout-relative without ..')
    candidate = checkout / relative
    walk = checkout
    for part in relative.parts:
        walk = walk / part
        if walk.is_symlink():
            raise ValueError('development_source: %s crosses a symlink; the grant covers real files only.' % relative.as_posix())
    resolved = candidate.resolve()
    if not resolved.is_relative_to(checkout.resolve()):
        raise ValueError('development_source: the path escapes the checkout.')
    if any(resolved == protected or resolved.is_relative_to(protected) for protected in _protected_roots(root)):
        raise ValueError('development_source: %s lies inside a protected root (serving checkout, Main or author drafts).' % relative.as_posix())
    if '.git' in relative.parts or relative.name in CREDENTIAL_NAMES or relative.suffix in CREDENTIAL_SUFFIXES:
        raise ValueError('development_source: %s is git internals or credential-shaped; never under a grant.' % relative.as_posix())
    posix = relative.as_posix()
    if not any(fnmatch.fnmatchcase(posix, pattern) for pattern in grant_row['paths']):
        raise ValueError('development_source: %s is outside the grant\'s permitted paths %s.' % (posix, grant_row['paths']))
    return candidate


def _pin(path: Path) -> str | None:
    return ('sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()) if path.is_file() else None


def read(root: Path, project: str, payload: dict, door: dict) -> dict:
    from laplace.projects import writing_sources
    _require(payload, 'read')
    _task, grant_row, checkout = _current(root, project, payload['grant_id'], 'read', door)
    path = _fenced(root, checkout, grant_row, payload['path'])
    if not path.is_file():
        return {'grant_id': grant_row['id'], 'path': Path(payload['path']).as_posix(), 'exists': False, 'sha256': None, 'bytes': 0, 'text': None}
    include_text = payload.get('include_text', True)
    if not isinstance(include_text, bool):
        raise ValueError('development_source: include_text must be a boolean.')
    observed = writing_sources.observe_bytes(path, {}, materialize=include_text)
    text = None
    if include_text:
        raw = observed['raw'] if observed.get('raw') is not None else path.read_bytes()
        try:
            text = raw.decode('utf-8') if len(raw) <= 64 * 1024 else None
        except UnicodeDecodeError:
            pass
    return {'grant_id': grant_row['id'], 'path': Path(payload['path']).as_posix(), 'exists': True, 'sha256': 'sha256:' + observed['sha256'],
            'bytes': observed['bytes'], 'text': text, 'base': grant_row['base'],
            'repository_read': {'operation': 'repository', 'payload': {'action': 'read', 'repository': grant_row['repository'],
                'path': Path(payload['path']).as_posix(), 'expected_sha256': 'sha256:' + observed['sha256'], 'offset': 0, 'limit': REVIEW_PAGE_CHARS}}}


def status(root: Path, project: str, payload: dict, door: dict) -> dict:
    """The development status page. Its WHOLE encoded result (collections, counts, continuations, notes and live allowance
    metadata) fits the shared delivery line (writing.delivery owner_line, else the navigation line nav.CAP) through
    _fitted. Nothing is clipped, hidden or capped; a continuation naming an old cut is refused."""
    from laplace.work import project_work
    from laplace.work import project_work_navigation as nav
    from laplace.writing import delivery
    _require(payload, 'status')
    task = project_work._tasks(project, root).get(payload['work_id'])
    if task is None:
        raise ValueError('development_source: name an existing Work id of this project.')
    current = cut(task, root)
    admit_cut(project, task, payload, current, 'development_source')
    offset, requested = int(payload.get('offset') or 0), int(payload.get('limit') or PAGE)
    grants = {row['id']: row for row in _latest_per_id(rows(task, 'grant'))}
    allowances = {}

    def allowance(row):
        from laplace.writing import source_execution
        if row['id'] not in allowances:
            allowances[row['id']] = {'grant_id': row['id'], **source_execution.status(root, source_execution.descriptor(
                project, row['work_id'], row['id'], row['parent_session_id'], row['native_allowance']))}
        return allowances[row['id']]

    extra = {'work': {'id': task['id'], 'title': task.get('title')}, 'lane': _public_lane(task, lane_row(task))}
    if payload.get('session_id'):
        extra.update(session_id=str(payload['session_id']), offers=_offers(root, project, task, str(payload['session_id'])))

    def wrap(development):
        result = {'development': development, 'status_notes': list(STATUS_NOTES), 'page_meaning': STATUS_PAGE_MEANING, **extra}
        if door.get('origin') == 'human':
            shown = [grants.get(item.get('id')) for item in ((development.get('grants') or {}).get('items') or ())]
            result['execution_allowances'] = [allowance(row) for row in shown if row and row.get('native_allowance')]
            result['allowance_observation'] = 'Live metadata outside the Source cut; no read or write authority is renewed.'
        return result
    if not task.get('development'):
        return wrap({'cut': current, 'grants': None, 'candidates': None, 'effects': None, 'checks': None})
    line = delivery.owner_line()
    result, fit = _fitted(task, root, offset, requested, nav.CAP if line is None else line, wrap)
    delivery.record_projection('status', fit)
    return result


def admit_cut(project: str, task: dict, payload: dict, current: str, operation: str) -> None:
    """The existing page-cut discipline (project_work_views: `as_of` against the view's cut): a continuation that names
    an old cut is refused with the exact restart of its series, never answered from a mixed state."""
    from laplace.work import project_work
    if payload.get('cut') and payload['cut'] != current:
        refusal = project_work.WorkConflict('%s rows changed between pages; old pages were not mixed.' % operation, project, task['id'],
                                            expected=payload['cut'], observed=current, field='cut')
        refusal.details['next_reads'] = [{'operation': operation, 'payload': {key: value for key, value in payload.items() if key not in {'cut', 'offset', 'project'}}}]
        refusal.details['restart_read'] = copy.deepcopy(refusal.details['next_reads'][0])   # the exact restart, typed
        raise refusal


# ------------------------------------------------------------------------------------------------ candidate and apply

def _edited_content(path: Path, item: dict) -> tuple[str, str, dict]:
    """Exact spans resolve against ONE bounded original; never against earlier replacements."""
    edits = item['edits']
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_COMPACT_EDITS:
        raise ValueError('development_source: compact edits require 1-%d exact spans.' % MAX_COMPACT_EDITS)
    if not path.is_file():
        raise ValueError('development_source: compact edits require an existing UTF-8 source.')
    with path.open('rb') as stream:
        raw = stream.read(MAX_CANDIDATE_BYTES + 1)
    if len(raw) > MAX_CANDIDATE_BYTES:
        raise ValueError('development_source: compact original exceeds the candidate byte ceiling.')
    pin = 'sha256:' + hashlib.sha256(raw).hexdigest()
    if item.get('before_sha256') != pin:
        raise ValueError('development_source: compact preimage changed; read it again.')
    try:
        original = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('development_source: compact edits require UTF-8 source.') from exc
    spans = []
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {'old', 'new'} or not isinstance(edit['old'], str) or not edit['old'] or not isinstance(edit['new'], str):
            raise ValueError('development_source: each edit has nonempty old text and new text.')
        start = original.find(edit['old'])
        if start < 0 or original.find(edit['old'], start + 1) >= 0:
            raise ValueError('development_source: each old span must occur exactly once in the original source.')
        spans.append((start, start + len(edit['old']), edit['new']))
    spans.sort()
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError('development_source: compact original spans overlap.')
    pieces, offset, delta, facts = [], 0, 0, []
    for index, (start, end, replacement) in enumerate(spans):
        pieces.extend((original[offset:start], replacement)); offset = end
        facts.append({'id': 'edit-%d' % (index + 1),
            'before': {'offset': start, 'chars': end - start, 'text': original[start:end]},
            'after': {'offset': start + delta, 'chars': len(replacement), 'text': replacement}})
        delta += len(replacement) - (end - start)
    pieces.append(original[offset:])
    result = ''.join(pieces)
    return result, pin, {'schema_version': VERIFIED_EDITS_SCHEMA, 'before_sha256': pin,
        'after_sha256': 'sha256:' + hashlib.sha256(result.encode('utf-8')).hexdigest(),
        'before_chars': len(original), 'after_chars': len(result), 'edits': facts}


def candidate(root: Path, project: str, payload: dict, door: dict) -> dict:
    from laplace.work import project_work
    _require(payload, 'candidate')
    task, grant_row, checkout = _current(root, project, payload['grant_id'], 'candidate', door)
    if not isinstance(payload['files'], list) or not 1 <= len(payload['files']) <= 32:
        raise ValueError('development_source: candidate files must contain 1-32 entries.')
    if any(isinstance(f, dict) and 'edits' in f for f in payload['files']):
        if len(json.dumps(payload['files'], ensure_ascii=False).encode('utf-8')) > MAX_CANDIDATE_BYTES:
            raise ValueError('development_source: compact input exceeds the candidate byte ceiling.')
    files, total, seen = [], 0, set()
    for item in payload['files']:
        if not isinstance(item, dict) or set(item) not in ({'path', 'before_sha256', 'content'}, {'path', 'before_sha256', 'edits'}):
            raise ValueError('development_source: each file has path/before_sha256 and exactly one of content or edits.')
        path = _fenced(root, checkout, grant_row, item['path'])
        relative = Path(item['path']).as_posix()
        if relative in seen:
            raise ValueError('development_source: a candidate names each path once.')
        seen.add(relative)
        if 'edits' in item:
            text, pin, verified = _edited_content(path, item)
        else:
            verified = None
            text, pin = item['content'], _pin(path)
            if not isinstance(text, str):
                raise ValueError('development_source: content must be UTF-8 text.')
        content = text.encode('utf-8')
        total += len(content)
        if item['before_sha256'] != pin:
            raise ValueError('development_source: %s preimage %s is not the file\'s current pin %s; read it again.' % (item['path'], item['before_sha256'], pin))
        files.append({'path': relative, 'before_sha256': pin, 'after_sha256': 'sha256:' + hashlib.sha256(content).hexdigest(), 'content': text,
                      **({'verified_edits': verified} if verified is not None else {})})
    if total > MAX_CANDIDATE_BYTES:
        raise ValueError('development_source: a candidate carries at most %d bytes.' % MAX_CANDIDATE_BYTES)
    ident = 'DC-' + _digest({'grant': grant_row['id'], 'files': [(f['path'], f['before_sha256'], f['after_sha256']) for f in files]})[7:31]
    with project_work.dispatch_lock(root):
        # Another equivalent compact/full submission may have won while we resolved
        # the preimage. Its immutable metadata is first-writer custody, never upgraded.
        current_task = project_work._tasks(project, root)[task['id']]
        if _latest(current_task, 'candidate', ident) is None:
            project_work._append(root, {'record': RECORD, 'kind': KINDS['candidate'], 'id': ident, 'work_id': task['id'], 'project': project,
                                        'grant_id': grant_row['id'], 'base': grant_row['base'], 'files': files, 'bytes': total, 'ts': _now(),
                                        'actor': _actor(root, project, payload, door)})
    return {'ok': True, 'candidate_id': ident, 'grant_id': grant_row['id'], 'base': grant_row['base'],
            'files': [{k: f[k] for k in ('path', 'before_sha256', 'after_sha256')} for f in files], 'bytes': total}


def _candidate_task(root, project, candidate_id):
    from laplace.work import project_work
    for task in project_work._tasks(project, root).values():
        if _latest(task, 'candidate', candidate_id) is not None:
            return task
    raise ValueError('development_source: unknown candidate %s.' % candidate_id)


def apply(root: Path, project: str, payload: dict, door: dict) -> dict:
    """One durable transaction per candidate; a retry after any cut reconciles the actual files and recovers the same request."""
    from laplace.manuscript import manuscript_source
    from laplace.work import project_work
    from laplace.manuscript import source_effects
    _require(payload, 'apply')
    ident = payload['candidate_id']
    effect_id = 'DE-' + _digest({'candidate': ident})[7:31]
    with project_work.dispatch_lock(root):
        task = _candidate_task(root, project, ident)
        cand = _latest(task, 'candidate', ident)
        history = [row for row in rows(task, 'effect') if row.get('id') == effect_id]
        latest = history[-1] if history else None
        if latest is not None and latest.get('state') in ('COMMITTED', 'ROLLED_BACK'):
            return {'ok': latest['state'] == 'COMMITTED', 'reused': True, 'effect': _public_effect(latest)}
        _task, grant_row, checkout = _current(root, project, cand['grant_id'], 'apply', door)
        actor = _actor(root, project, payload, door)
        targets = [(item, _fenced(root, checkout, grant_row, item['path'])) for item in cand['files']]
        if latest is None:
            # the prepared transaction is durable BEFORE any byte moves: exact originals, intended postimages, the original actor
            for item, path in targets:
                if _pin(path) != item['before_sha256']:
                    raise ValueError('development_source: %s changed since the candidate (pin %s); prepare a new candidate.' % (item['path'], _pin(path)))
            prepared = {'record': RECORD, 'kind': KINDS['effect'], 'id': effect_id, 'work_id': task['id'], 'project': project, 'candidate_id': ident,
                        'grant_id': grant_row['id'], 'base': grant_row['base'], 'state': 'PREPARED', 'ts': _now(), 'actor': actor, 'attempt': 1,
                        'files': [{'path': item['path'], 'before_sha256': item['before_sha256'], 'after_sha256': item['after_sha256'], 'state': 'PREPARED'} for item, _ in targets]}
            project_work._append(root, prepared)
            original_actor, attempt = actor, 1
        else:
            original_actor, attempt = latest.get('actor') or actor, int(latest.get('attempt') or 1) + 1
        with manuscript_source.source_mutation([path for _, path in targets], timeout=15.0):
            receipts, written, failure = [], [], None
            for item, path in targets:
                current = _pin(path)
                before = path.read_bytes() if path.is_file() else None
                data = item['content'].encode('utf-8')
                if current == item['after_sha256']:
                    receipts.append({**source_effects.observed_file(checkout, path, before, data), 'state': 'ALREADY_APPLIED'})
                    continue
                if current != item['before_sha256']:
                    receipts.append({**source_effects.observed_file(checkout, path, before, data), 'state': 'DIVERGED'})
                    continue
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    source_effects.replace(path, data)
                    written.append((item, path, before))
                    receipts.append({**source_effects.observed_file(checkout, path, before, data), 'state': 'COMMITTED'})
                except Exception as exc:
                    failure = {'path': item['path'], 'error': str(exc)[:400]}
                    receipts.append({**source_effects.observed_file(checkout, path, before, data), 'state': 'FAILED'})
                    # compensate this attempt's own writes, each only where the file still holds this operation's postimage
                    for done_item, done, previous in reversed(written):
                        receipt_row = next(r for r in receipts if r['path'] == done.resolve().relative_to(checkout.resolve()).as_posix())
                        if _pin(done) != done_item['after_sha256']:
                            receipt_row.update(state='DIVERGED')
                            continue
                        try:
                            if previous is None:
                                done.unlink(missing_ok=True)
                            else:
                                source_effects.replace(done, previous)
                            receipt_row.update(source_effects.observed_file(checkout, done, previous, previous), state='ROLLED_BACK')
                        except Exception as rollback_error:
                            receipt_row.update(state='PARTIAL', rollback_error=str(rollback_error)[:400])
                    break
        states = {row['state'] for row in receipts}
        if states <= {'COMMITTED', 'ALREADY_APPLIED'}:
            state = 'COMMITTED'
        elif states <= {'ROLLED_BACK', 'FAILED'}:
            state = 'ROLLED_BACK'
        elif states == {'DIVERGED'}:
            state = 'DIVERGED'      # every file moved under someone else's hand since the prepared row: nothing was touched
        else:
            state = 'PARTIAL'
        published = {'record': RECORD, 'kind': KINDS['effect'], 'id': effect_id, 'work_id': task['id'], 'project': project, 'candidate_id': ident,
                     'grant_id': grant_row['id'], 'base': grant_row['base'], 'state': state, 'files': receipts, 'failure': failure, 'ts': _now(),
                     'actor': original_actor, 'attempt': attempt, **({'recovered_by': actor} if attempt > 1 else {}),
                     'receipt': source_effects.receipt(project, {'grant_id': grant_row['id'], 'candidate_id': ident, 'base': grant_row['base']},
                                                       [{k: v for k, v in r.items() if k in ('scope', 'path', 'before_sha256', 'after_sha256', 'observed_after_sha256', 'observation_error')} for r in receipts],
                                                       complete=state == 'COMMITTED')}
        project_work._append(root, published)
    return {'ok': state == 'COMMITTED', 'effect': _public_effect(published)}


def _public_effect(row: dict) -> dict:
    return {key: row.get(key) for key in ('id', 'candidate_id', 'grant_id', 'base', 'state', 'files', 'failure', 'ts', 'attempt', 'recovered_by')}


# ------------------------------------------------------------------------------------------------ qualified Work review

def _review_pins(pins, *, allow_empty=False):
    if not isinstance(pins, dict) or len(pins) > 64 or (not pins and not allow_empty):
        raise ValueError('development_source: review/fixed pins map at most 64 exact relative paths to SHA256.')
    for path, pin in pins.items():
        if not isinstance(path, str) or not path or Path(path).is_absolute() or '..' in Path(path).parts or '\\' in path or Path(path).as_posix() != path or path == '.' \
                or not isinstance(pin, str) or not _SHA.fullmatch(pin):
            raise ValueError('development_source: pins require canonical relative paths and sha256:<64 lower hex>.')


def _review_records(root, project, work_id, selection):
    if not isinstance(selection, dict) or set(selection) != {'grant_id', 'candidate_id'} or any(not isinstance(v, str) or not v for v in selection.values()):
        raise ValueError('development_source: source basis selects exactly grant_id and candidate_id.')
    task, grant_row = _find_grant(root, project, selection['grant_id'])
    if task['id'] != work_id:
        raise ValueError('development_source: source basis belongs to another Work.')
    cand = _latest(task, 'candidate', selection['candidate_id'])
    if cand is None or cand.get('grant_id') != grant_row['id'] or cand.get('base') != grant_row['base']:
        raise ValueError('development_source: candidate does not belong to this grant and base.')
    effect = _latest(task, 'effect', 'DE-' + _digest({'candidate': cand['id']})[7:31])
    if effect is None or effect.get('state') != 'COMMITTED' or effect.get('candidate_id') != cand['id'] \
            or effect.get('grant_id') != grant_row['id'] or effect.get('base') != grant_row['base']:
        raise ValueError('development_source: review requires the completed committed candidate effect.')
    return task, grant_row, cand, effect


def _review_identity(project, work_id, grant_row, cand, effect):
    return {'schema_version': REVIEW_BASIS_SCHEMA, 'project': project, 'work_id': work_id,
        'grant_id': grant_row['id'], 'candidate_id': cand['id'], 'effect_id': effect['id'],
        'repository': grant_row['repository'], 'checkout_identity': _digest(grant_row['checkout']), 'base': grant_row['base']}


def _review_authority(root, project, task, grant_row, door, pins):
    """Historical inspection authority, NOT a renewed write grant or a new expiry."""
    acting = _acting(root, project, door)
    if acting['kind'] == 'human':
        return
    session = acting.get('session_id')
    if acting.get('role') == 'review':
        from laplace.work import work_delivery
        admitted = any(row.get('state') in {'RESERVED', 'DELIVERED', 'ADMITTED'} and row.get('session_id') == session
            and (row.get('recipient') or {}).get('id') == grant_row.get('evaluator')
            and (row.get('recipient') or {}).get('revision') == grant_row.get('evaluator_revision')
            for row in work_delivery._rows(task, work_delivery.EVENT))
        if not admitted:
            raise ValueError('development_source: review admission requires the actual original evaluator delivery session and binding revision.')
    elif session == grant_row.get('parent_session_id'):
        return
    elif session in (grant_row.get('delegates') or {}):
        subset = grant_row['delegates'][session]
        if 'read' not in subset['operations'] or any(not any(fnmatch.fnmatchcase(path, pattern) for pattern in subset['paths']) for path in pins):
            raise ValueError('development_source: review basis exceeds the original delegate read subset.')
    else:
        raise ValueError('development_source: review admission requires an actual Source holder or admitted evaluator.')


def prepare_review_basis(root: Path, project: str, work_id: str, selection: dict, pins: dict, *, door: dict) -> dict:
    """Pure fresh handoff admission. Work owns covered-obligation coverage; Source owns actual bytes/effect/authority."""
    _review_pins(pins)
    task, grant_row, cand, effect = _review_records(root, project, work_id, selection)
    _current_task, effective, checkout = _current(root, project, grant_row['id'], 'read', door)
    _review_authority(root, project, task, grant_row, door, pins)
    # A handoff includes every changed postimage, even when a later review consumes only a subset.
    if any(pins.get(item['path']) != item['after_sha256'] for item in cand['files']):
        raise ValueError('development_source: handoff pins must include every candidate postimage.')
    for path, expected in pins.items():
        if _pin(_fenced(root, checkout, effective, path)) != expected:
            raise ValueError('development_source: handoff source changed or unavailable: ' + path)
    return copy.deepcopy({**_review_identity(project, work_id, grant_row, cand, effect), 'pins': dict(pins)})


def validate_review_basis(root: Path, project: str, work_id: str, basis: dict, *, consumed_pins=None, door=None, read_context=None) -> dict:
    """Pure canonical recorded-basis currentness; expiry never erases completed source evidence.

    Work must pass only its own retained basis. With a door this also proves actual review-admission identity;
    that authority refusal raises. No-door currentness grants no new reads, write, review or acceptance authority.
    """
    observed = {}
    def outcome(status, reason):
        return {'status': status, 'reason': reason, 'observed_pins': dict(observed)}
    try:
        if not isinstance(basis, dict):
            raise ValueError('recorded source basis is absent')
        _review_pins(basis.get('pins'))
        task, grant_row, cand, effect = _review_records(root, project, work_id,
            {key: basis.get(key) for key in ('grant_id', 'candidate_id')})
        identity = _review_identity(project, work_id, grant_row, cand, effect)
        if set(basis) != set(identity) | {'pins'} or any(basis.get(k) != v for k, v in identity.items()):
            raise ValueError('recorded source identity does not match this Work/grant/candidate/effect')
        if any(basis['pins'].get(item['path']) != item['after_sha256'] for item in cand['files']):
            raise ValueError('recorded source basis omits candidate postimages')
        pins = basis['pins'] if consumed_pins is None else consumed_pins
        _review_pins(pins)
        if any(basis['pins'].get(path) != expected for path, expected in pins.items()):
            raise ValueError('consumed pins are not an identical subset of recorded source pins')
    except (ValueError, KeyError, TypeError) as exc:
        return outcome('UNKNOWN', str(exc)[:500])
    if door is not None:
        _review_authority(root, project, task, grant_row, door, pins)
    try:
        configured=basis_checkout(root, project, work_id, grant_row['repository'], 'currentness')
        from laplace.work import development_adoption   # D5: an ADOPTED lane's basis is anchored on its adoption commit
        adopted = development_adoption.anchor(root, project, work_id, grant_row)
        checkout = adopted['checkout'] if adopted else Path(grant_row['checkout'])   # :1311 adopted: the resolver's answer is the checkout
        from laplace.work.project_work_review import observe_fact_input
        observe_fact_input(root,read_context,['qualified-repository',project,work_id],{'checkout':str(configured)})
        if configured != checkout:
            return outcome('CHANGED', 'the configured source repository was retargeted')
        if adopted is None:   # :1313 adopted: the live root is read for this currentness only (anchor().pin), never written
            _refuse_checkout(root, checkout)
        current_base=_base(checkout)
        observe_fact_input(root,read_context,['qualified-base',project,work_id],{'base':current_base})
        if adopted is None and current_base != grant_row['base']:
            return outcome('CHANGED', 'the recorded source checkout base changed')
        if adopted is not None and not adopted['in_history']:   # :1316 adopted: A is live HEAD or its ancestor
            return outcome('CHANGED', 'the adoption commit is no longer in live history')
        for path, expected in pins.items():
            observed[path] = adopted['pin'](path) if adopted else _pin(_fenced(root, checkout, grant_row, path))
        if any(pin is None for pin in observed.values()):
            return outcome('UNKNOWN', 'a consumed source file is unavailable')
        if any(observed[path] != expected for path, expected in pins.items()):
            return outcome('CHANGED', 'consumed source bytes changed')
    except (OSError, ValueError) as exc:
        return outcome('UNKNOWN', str(exc)[:500])
    return outcome('CURRENT', 'the exact recorded qualified source and consumed pins still match')


def validate_review_recipient(root: Path, project: str, work_id: str, basis: dict, recipient: dict) -> None:
    """Pure original evaluator identity check; delivery owns current approval/expiry.

    This does not grant a session authority or assert current source bytes. Delivery
    separately validates its consumed source pins before reserving any transport.
    """
    if not isinstance(basis, dict):
        raise ValueError('development_source: recorded Source basis is absent')
    task, grant_row, cand, effect = _review_records(root, project, work_id,
        {key: basis.get(key) for key in ('grant_id', 'candidate_id')})
    identity = _review_identity(project, work_id, grant_row, cand, effect)
    if set(basis) != set(identity) | {'pins'} or any(basis.get(key) != value for key, value in identity.items()):
        raise ValueError('development_source: recorded Source identity does not match this Work/grant/candidate/effect')
    _review_pins(basis['pins'])
    if not isinstance(recipient, dict) or recipient.get('id') != grant_row.get('evaluator') \
            or recipient.get('revision') != grant_row.get('evaluator_revision'):
        raise ValueError('development_source: delivery requires the original Source evaluator binding and revision')


# ------------------------------------------------------------------------------------------------ cumulative review subject

#: Stage meaning carried with every typed stage (Root stage adjudication 2026-11-02).
STAGE_MEANING = ('Root-declared acceptance stage of THIS review. pre_source_review criteria are judged now from the named evidence; '
                 'post_adoption criteria remain later typed obligations that this review neither satisfies nor waives.')


def _commission_grants(task, grant_row):
    """The grants of this Work that are ONE commission's production: the same configured repository, checkout and base
    and, where a commission is declared, the same commission request id (grant reissue never resets it). Ledger order."""
    policy = (grant_row.get('native_allowance') or {}).get('commission_request_id')
    return [row for row in _latest_per_id(rows(task, 'grant'))
            if row.get('repository') == grant_row['repository'] and row.get('checkout') == grant_row['checkout']
            and row.get('base') == grant_row['base'] and (row.get('native_allowance') or {}).get('commission_request_id') == policy]


def _commission_chains(task, grant_ids):
    """Every COMMITTED effect of those grants in application order, and per changed path its exact effect chain."""
    effects, chains = [], {}
    for effect in _latest_per_id(rows(task, 'effect')):
        if effect.get('grant_id') not in grant_ids or effect.get('state') != 'COMMITTED':
            continue
        cand = _latest(task, 'candidate', effect.get('candidate_id'))
        if cand is None or cand.get('grant_id') != effect['grant_id']:
            raise ValueError('development_source: committed effect %s has no retained candidate of its grant.' % effect['id'])
        changed = []
        for item in cand['files']:
            if item['before_sha256'] == item['after_sha256']:
                continue
            changed.append(item['path'])
            chains.setdefault(item['path'], []).append({'effect_id': effect['id'], 'candidate_id': cand['id'], 'grant_id': effect['grant_id'],
                'before_sha256': item['before_sha256'], 'after_sha256': item['after_sha256'], 'verified_change_facts': 'verified_edits' in item})
        effects.append({'id': effect['id'], 'candidate_id': cand['id'], 'grant_id': effect['grant_id'], 'ts': effect.get('ts'), 'files': changed})
    return effects, chains


def _base_blob_text(checkout, base, path, expected):
    """The immutable base commit's blob for path, only when its exact raw bytes ARE the retained preimage pin."""
    if not base or not isinstance(expected, str):
        return None
    try:
        out = subprocess.run(['git', '-C', str(checkout), 'show', '%s:%s' % (base, path)], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or 'sha256:' + hashlib.sha256(out.stdout).hexdigest() != expected:
        return None
    try:
        return out.stdout.decode('utf-8')
    except UnicodeDecodeError:
        return None


def _retained_preimage_text(task, link, path, checkout=None):
    """The exact retained raw preimage of a commission's FIRST change to path: '' for a created file, reconstructed from
    the candidate's own verified edit facts (checked against both pins), or None when no retained bytes prove it."""
    cand = _latest(task, 'candidate', link['candidate_id'])
    item = next((f for f in (cand or {}).get('files') or () if f['path'] == path), None)
    if item is None:
        return None
    if item['before_sha256'] is None:
        return ''
    if 'verified_edits' not in item or not isinstance(item.get('content'), str):
        return _base_blob_text(checkout, cand.get('base'), path, item['before_sha256']) if checkout is not None else None
    try:
        facts = _checked_edit_facts(item, item['content'])
    except (ValueError, KeyError, TypeError):
        return _base_blob_text(checkout, cand.get('base'), path, item['before_sha256']) if checkout is not None else None
    text, chunks, cursor = item['content'], [], 0
    for edit in facts['edits']:
        after = edit['after']
        chunks.extend((text[cursor:after['offset']], edit['before']['text']))
        cursor = after['offset'] + after['chars']
    chunks.append(text[cursor:])
    return ''.join(chunks)


def _line_hunks(before, after):
    """Line hunks of retained preimage -> current postimage in repository reader units (universal newlines)."""
    import difflib
    a, b = _reader_text(before).splitlines(keepends=True), _reader_text(after).splitlines(keepends=True)
    hunks = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != 'equal':
            hunks.append({'id': 'hunk-%d' % (len(hunks) + 1), 'tag': tag, 'before_lines': [i1 + 1, i2], 'after_lines': [j1 + 1, j2]})
    return hunks


def _cumulative_file(root, task, checkout, path, chain):
    """One commission-changed path: its whole effect chain, retained preimage, current postimage and derived geometry."""
    first, last = chain[0], chain[-1]
    target = _dependency_path(root, checkout, (), path)
    current = _pin(target) if target.is_file() else None
    if current != last['after_sha256']:
        raise ValueError('development_source: commission file %s no longer holds its last committed postimage (%s); the cumulative subject changed.'
                         % (path, current))
    continuous = all(a['after_sha256'] == b['before_sha256'] for a, b in zip(chain, chain[1:]))
    geometry = {'state': 'DERIVED', 'hunks': [], 'hunks_total': 0,
                'basis': 'retained raw preimage -> current committed postimage (line diff); never a replay of earlier candidate offsets'}
    if not continuous:
        geometry['state'] = 'CHAIN_DISCONTINUOUS'
    else:
        before = _retained_preimage_text(task, first, path, checkout)
        raw = target.read_bytes()
        if before is None:
            geometry['state'] = 'UNKNOWN_BASELINE'
        elif len(raw) > MAX_CANDIDATE_BYTES or len(before.encode('utf-8')) > MAX_CANDIDATE_BYTES:
            geometry['state'] = 'EXCEEDS_GEOMETRY_CEILING'
        else:
            try:
                after = raw.decode('utf-8')
            except UnicodeDecodeError:
                after = None
            if after is None or '\x00' in after:
                geometry['state'] = 'NOT_PLAIN_UTF8'
            else:
                hunks = _line_hunks(before, after)
                if len(hunks) > MAX_SUBJECT_HUNKS:
                    geometry.update(state='HUNKS_EXCEED_BOUND', hunks_total=len(hunks))
                else:
                    geometry.update(hunks=hunks, hunks_total=len(hunks))
    baseline = 'ABSENT' if first['before_sha256'] is None else 'UNKNOWN' if geometry['state'] == 'UNKNOWN_BASELINE' else 'PINNED'
    return {'path': path, 'retained_preimage': first['before_sha256'], 'current_postimage': last['after_sha256'], 'baseline': baseline,
            'chain_continuous': continuous, 'effects': copy.deepcopy(chain), 'geometry': geometry}


def _plan_cumulative(row):
    """The per-input projection of one subject change that a reading plan carries."""
    return {key: copy.deepcopy(row[key]) for key in ('retained_preimage', 'current_postimage', 'baseline', 'chain_continuous', 'geometry')} \
        | {'effect_ids': [link['effect_id'] for link in row['effects']]}


#: At most this many explicitly selected prior grants join one review subject (F1); each keeps its own attribution.
MAX_PRIOR_GRANTS = 16
_BASE_TREES, _BASE_BLOBS = {}, {}


def _prior_production(task, grant_row, grants, spec):
    """The EXPLICITLY selected earlier production of separately attributed commissions of this SAME Work and original parent
    (F1): grants of this Work's ledger on the same repository, checkout and base, under the same original parent session,
    outside this commission, each with committed production. Selection joins their committed effects and change chains to
    the review subject with their own attribution; their accounts, quotas and write authority stay separate (nothing here
    widens a grant). Foreign or conflicting ancestry refuses; nothing is inferred from a latest or any-other grant."""
    if not isinstance(spec, dict) or set(spec) != {'grants'} or not isinstance(spec['grants'], list) \
            or not 1 <= len(spec['grants']) <= MAX_PRIOR_GRANTS or any(not isinstance(ident, str) for ident in spec['grants']) \
            or len(set(spec['grants'])) != len(spec['grants']):
        raise ValueError('development_source: source_subject.prior is {grants: [1-%d distinct prior grant ids of this Work]}.' % MAX_PRIOR_GRANTS)
    known = {row['id']: row for row in _latest_per_id(rows(task, 'grant'))}
    own = {row['id'] for row in grants}
    parent = (grants[0] if grants else grant_row).get('parent_session_id')
    committed = {row.get('grant_id') for row in _latest_per_id(rows(task, 'effect')) if row.get('state') == 'COMMITTED'}
    selected = []
    for ident in spec['grants']:
        row = known.get(ident)
        if row is None:
            raise ValueError('development_source: prior grant %s is not a grant of this Work (foreign ancestry).' % ident)
        if ident in own:
            raise ValueError('development_source: prior grant %s already belongs to this commission; name only separately attributed production.' % ident)
        if any(row.get(key) != grant_row.get(key) for key in ('repository', 'checkout', 'base')):
            raise ValueError('development_source: prior grant %s names another repository, checkout or base (conflicting ancestry).' % ident)
        if row.get('parent_session_id') != parent:
            raise ValueError('development_source: prior grant %s belongs to another original parent session (conflicting ancestry).' % ident)
        if ident not in committed:
            raise ValueError('development_source: prior grant %s has no committed production to review.' % ident)
        selected.append(row)
    return selected


def _base_tree(checkout, commit):
    """{path: blob object id} of one immutable commit's whole tree in this checkout, or None when it is not readable."""
    import re
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}(?:[0-9a-f]{24})?', commit):
        return None
    key = (str(checkout), commit)
    if key not in _BASE_TREES:
        try:
            out = subprocess.run(['git', '-C', str(checkout), 'ls-tree', '-r', '-z', '--full-tree', commit], capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        tree = {}
        for entry in out.stdout.split(b'\0'):
            meta, tab, name = entry.partition(b'\t')
            parts = meta.split()
            if tab and len(parts) == 3 and parts[1] == b'blob':
                tree[name.decode('utf-8', 'surrogateescape')] = parts[2].decode('ascii')
        while len(_BASE_TREES) >= 4:
            _BASE_TREES.pop(next(iter(_BASE_TREES)))
        _BASE_TREES[key] = tree
    return _BASE_TREES[key]


def _git_blob_id(data, width):
    return (hashlib.sha256 if width == 64 else hashlib.sha1)(b'blob %d\0' % len(data) + data).hexdigest()


def _carry_base_relation(tree, relative, path):
    """A carry member outside the subject's changes, against the declared base tree (F1): UNCHANGED_CARRY only when its
    exact bytes ARE the base blob; CHANGED_SINCE_BASE or ADDED_SINCE_BASE when they differ from it or the base has no
    such file; BASE_UNKNOWN when the base tree is unreadable. A matching pin proves only that the member has not drifted
    since it was pinned, never that earlier production left it unchanged."""
    if tree is None:
        return 'BASE_UNKNOWN'
    oid = tree.get(relative)
    if oid is None:
        return 'ADDED_SINCE_BASE'
    return 'UNCHANGED_CARRY' if _git_blob_id(path.read_bytes(), len(oid)) == oid else 'CHANGED_SINCE_BASE'


def _changed_base_relation(checkout, tree, row):
    """Where a subject-changed path's FIRST retained preimage stands against the declared base (F1): PREIMAGE_AT_BASE,
    CREATED_BY_SUBJECT, CHANGED_BEFORE_SUBJECT (production outside this subject changed it after the base; select that
    prior production explicitly to review it) or BASE_UNKNOWN. Read-only; the retained preimage pin itself is unchanged."""
    path, before = row['path'], row['retained_preimage']
    if tree is None:
        return 'BASE_UNKNOWN'
    if path not in tree:
        return 'CREATED_BY_SUBJECT' if before is None else 'CHANGED_BEFORE_SUBJECT'
    if before is None:
        return 'CHANGED_BEFORE_SUBJECT'
    key = (str(checkout), tree[path])
    if key not in _BASE_BLOBS:
        try:
            out = subprocess.run(['git', '-C', str(checkout), 'cat-file', 'blob', tree[path]], capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return 'BASE_UNKNOWN'
        if out.returncode != 0:
            return 'BASE_UNKNOWN'
        if len(_BASE_BLOBS) >= 8192:
            _BASE_BLOBS.clear()
        _BASE_BLOBS[key] = 'sha256:' + hashlib.sha256(out.stdout).hexdigest()
    return 'PREIMAGE_AT_BASE' if _BASE_BLOBS[key] == before else 'CHANGED_BEFORE_SUBJECT'


def _review_carry(root, project, grant_row, checkout, changed, spec, tree=None):
    """ONE explicitly admitted READ-ONLY carry manifest (inline or pinned project Artifact, the existing manifest owner).

    Every member is fenced (no symlink, inside the checkout, not git/credential/protected) and current: an unchanged
    member equals its pin; a member the commission changed must equal that change's retained preimage or current
    postimage, otherwise the manifest is a stale or foreign cut. A carry never becomes write authority or a check input."""
    value, source = _manifest_value(root, project, spec, role='review-carry')
    members = value.get('members') if isinstance(value, dict) else None
    if not isinstance(value, dict) or value.get('schema') not in (REVIEW_CARRY_SCHEMA, *DEPENDENCY_MANIFEST_SCHEMAS) \
            or not isinstance(members, list) or not members:
        raise ValueError('development_source: a review carry manifest has schema %s and a nonempty members list.' % REVIEW_CARRY_SCHEMA)
    if value.get('repository', grant_row['repository']) != grant_row['repository'] or value.get('base', grant_row['base']) != grant_row['base']:
        raise ValueError('development_source: the review carry manifest names another repository or base (foreign manifest).')
    if len(members) > MAX_DEPENDENCY_MANIFEST_MEMBERS:
        raise ValueError('development_source: review carry has %d members, above the bound %d.' % (len(members), MAX_DEPENDENCY_MANIFEST_MEMBERS))
    kept, seen, problems, total = [], set(), [], 0
    for row in members:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str) or not isinstance(row.get('sha256'), str) or not _SHA.fullmatch(row['sha256']):
            raise ValueError('development_source: every review carry member is {path, sha256:<64 hex>}.')
        relative = row['path']
        if not relative or Path(relative).as_posix() != relative or relative in seen:
            raise ValueError('development_source: review carry member %s is not canonical or is named twice.' % relative)
        seen.add(relative)
        try:
            path = _dependency_path(root, checkout, (), relative)
        except ValueError as exc:
            problems.append(str(exc).removeprefix('development_source: '))
            continue
        current = _pin(path) if path.is_file() else None
        link = changed.get(relative)
        if link is not None:
            relation = ('COMMISSION_PREIMAGE' if row['sha256'] == link['retained_preimage']
                        else 'COMMISSION_POSTIMAGE' if row['sha256'] == link['current_postimage'] else None)
            if relation is None:
                problems.append('member %s is neither the retained preimage nor the current postimage of its commission change (stale or foreign cut)' % relative)
                continue
        elif current != row['sha256']:
            problems.append('member %s %s' % (relative, 'is missing' if current is None else 'drifted from its read-only pin'))
            continue
        else:
            relation = _carry_base_relation(tree, relative, path)
        total += path.stat().st_size if path.is_file() else 0
        kept.append({'path': relative, 'sha256': row['sha256'], 'relation': relation})
    if problems:
        raise ValueError('development_source: read-only review carry refused (%d of %d members): %s' % (len(problems), len(members), '; '.join(problems[:8])))
    if total > MAX_DEPENDENCY_CLOSURE_BYTES:
        raise ValueError('development_source: review carry is %d bytes, above the bound %d.' % (total, MAX_DEPENDENCY_CLOSURE_BYTES))
    kept.sort(key=lambda item: item['path'])
    return {'schema': REVIEW_CARRY_SCHEMA, 'source': source, 'digest': _digest([(item['path'], item['sha256']) for item in kept]),
            'members': kept, 'members_total': len(kept), 'bytes_total': total,
            'authority': 'Read-only review subject and currentness basis. Never Source write authority, a check input or accepted by inclusion.'}


def _review_stage(stage):
    """A typed, bounded acceptance stage: what THIS review judges now and what remains a later obligation."""
    if not isinstance(stage, dict) or not {'id', 'pre_source_review', 'post_adoption'} <= set(stage) \
            or set(stage) - {'id', 'pre_source_review', 'post_adoption', 'authority', 'summary'}:
        raise ValueError('development_source: a review stage has id, pre_source_review, post_adoption[, authority, summary].')
    if not isinstance(stage['id'], str) or not 1 <= len(stage['id']) <= 96:
        raise ValueError('development_source: a review stage id is 1-96 characters.')
    criteria = {}
    for key, minimum in (('pre_source_review', 1), ('post_adoption', 0)):
        items = stage[key]
        if not isinstance(items, list) or not minimum <= len(items) <= MAX_STAGE_CRITERIA \
                or any(not isinstance(text, str) or not 1 <= len(text) <= MAX_STAGE_TEXT for text in items):
            raise ValueError('development_source: stage %s lists %d-%d criteria of at most %d characters.' % (key, minimum, MAX_STAGE_CRITERIA, MAX_STAGE_TEXT))
        criteria[key] = list(items)
    authority = stage.get('authority', [])
    if not isinstance(authority, list) or len(authority) > MAX_STAGE_AUTHORITY or any(
            not isinstance(ref, dict) or set(ref) != {'path', 'sha256'} or not isinstance(ref['path'], str) or not 1 <= len(ref['path']) <= 400
            or not isinstance(ref['sha256'], str) or not _SHA.fullmatch(ref['sha256']) for ref in authority):
        raise ValueError('development_source: stage authority is at most %d exact {path, sha256:<64 hex>} evidence references.' % MAX_STAGE_AUTHORITY)
    summary = stage.get('summary', '')
    if not isinstance(summary, str) or len(summary) > MAX_STAGE_SUMMARY:
        raise ValueError('development_source: a stage summary has at most %d characters.' % MAX_STAGE_SUMMARY)
    return {'id': stage['id'], **criteria, 'authority': copy.deepcopy(authority), 'summary': summary, 'meaning': STAGE_MEANING}


def review_subject(root: Path, project: str, work_id: str, basis: dict, request=None) -> dict:
    """PURE canonical cumulative review subject of one qualified Source basis; no write, read grant or acceptance.

    Derived from this Work's Source rows: every COMMITTED effect of the commission across reissued grants (same
    configured checkout/base/commission), each changed path's chain and geometry from retained preimage to current
    postimage, plus the separately admitted read-only carry and typed stage of `request` {carry?, stage?}. The basis'
    latest candidate/effect is kept as latest_delta, the exact anchor. Unknown baselines/geometry stay explicit."""
    if request is not None and (not isinstance(request, dict) or set(request) - {'carry', 'stage', 'prior', 'accepted_base'}):
        raise ValueError('development_source: source_subject has only carry, stage, prior and accepted_base.')
    request = copy.deepcopy(request or {})
    task, grant_row, cand, effect = _review_records(root, project, work_id, {key: (basis or {}).get(key) for key in ('grant_id', 'candidate_id')})
    checkout = Path(grant_row['checkout'])
    grants = _commission_grants(task, grant_row)
    prior = _prior_production(task, grant_row, grants, request['prior']) if 'prior' in request else []
    effects, chains = _commission_chains(task, {row['id'] for row in grants} | {row['id'] for row in prior})
    if effect['id'] not in {row['id'] for row in effects}:
        raise ValueError('development_source: the latest delta is not a committed effect of its commission.')
    changed = [_cumulative_file(root, task, checkout, path, chains[path]) for path in sorted(chains)]
    by_path = {row['path']: row for row in changed}
    # F1: change provenance against the DECLARED accepted base (else the grant's recorded base): an explicitly declared
    # base must be a readable commit of this checkout; an unreadable default base stays BASE_UNKNOWN, never 'unchanged'.
    base_commit = request.get('accepted_base', grant_row['base'])
    tree = _base_tree(checkout, base_commit)
    if 'accepted_base' in request and tree is None:
        raise ValueError('development_source: the declared accepted base %s is not a readable commit of this checkout.' % str(base_commit)[:80])
    for row in changed:
        row['base_relation'] = _changed_base_relation(checkout, tree, row)
    carry = _review_carry(root, project, grant_row, checkout, by_path, request['carry'], tree) if 'carry' in request else None
    stage = _review_stage(request['stage']) if 'stage' in request else None
    carry_paths = {row['path'] for row in (carry or {}).get('members') or ()}
    subject = {'schema_version': REVIEW_SUBJECT_SCHEMA, 'project': project, 'work_id': work_id,
        'repository': grant_row['repository'], 'checkout_identity': _digest(grant_row['checkout']), 'base': grant_row['base'], 'request': request,
        'commission': {'commission_request_id': (grant_row.get('native_allowance') or {}).get('commission_request_id'),
                       'original_parent_session_id': grants[0].get('parent_session_id'),
                       'grants': [{'id': row['id'], 'parent_session_id': row.get('parent_session_id'), 'paths': list(row.get('paths') or ())} for row in grants]},
        'effects': effects, 'changed_files': changed,
        'latest_delta': {'grant_id': grant_row['id'], 'candidate_id': cand['id'], 'effect_id': effect['id'],
                         'files': [{key: item[key] for key in ('path', 'before_sha256', 'after_sha256')} for item in cand['files']],
                         'meaning': 'Exact anchor: the most recent committed Source change. One delta of the subject, never the review scope.'},
        'readonly_carry': carry if carry is not None else {'state': 'NOT_DECLARED',
            'meaning': 'No read-only carry was admitted; inherited source outside the commission changes is not part of this subject.'},
        'stage': stage if stage is not None else {'state': 'NOT_DECLARED'},
        'union': {'paths_total': len(set(by_path) | carry_paths), 'commission_changed': len(by_path), 'carry_members': len(carry_paths),
                  'carry_outside_changes': len(carry_paths - set(by_path)), 'effects': len(effects), 'grants': len(grants)},
        'semantic_adequacy': 'UNASSESSED', 'offered_not_observed': True,
        'meaning': ('The whole review subject: every changed path and carry member is in scope. Pins identify bytes and are not reads; '
                    'structural plan completeness is not reading, semantic acceptance or functional proof.')}
    subject['base_relation'] = {'commit': base_commit, 'declared': 'accepted_base' in request, 'tree': 'UNAVAILABLE' if tree is None else 'READABLE',
        'meaning': ('Each changed path and carry member is compared with this base tree. Pins identify bytes; only the base tree says whether '
                    'they changed since the base. CHANGED_BEFORE_SUBJECT names production outside this subject.')}
    if prior:
        attributed = {row['id'] for row in prior}
        subject['prior_production'] = {
            'grants': [{'id': row['id'], 'commission_request_id': (row.get('native_allowance') or {}).get('commission_request_id'),
                        'parent_session_id': row.get('parent_session_id'), 'paths': list(row.get('paths') or ())} for row in prior],
            'effects': [row['id'] for row in effects if row['grant_id'] in attributed],
            'meaning': ('Explicitly selected earlier production of separately attributed commissions of this Work and original parent. It is '
                        'review scope with its own attribution, effects and change chains; its accounts, quotas, write authority and '
                        'recorded reviews stay separate and nothing is accepted by inclusion.')}
        subject['union'].update(prior_grants=len(prior), prior_effects=len(subject['prior_production']['effects']))
    subject['subject_id'] = 'DRS-' + _digest(subject)[7:]
    return copy.deepcopy(subject)


def validate_review_subject(root: Path, project: str, work_id: str, basis: dict, subject: dict) -> dict:
    """Pure currentness of a recorded cumulative subject, recomputed now from the same basis and request."""
    try:
        if not isinstance(subject, dict) or subject.get('schema_version') != REVIEW_SUBJECT_SCHEMA:
            raise ValueError('the recorded review subject is absent or of another version')
        if subject.get('subject_id') != 'DRS-' + _digest({key: value for key, value in subject.items() if key != 'subject_id'})[7:]:
            raise ValueError('the recorded review subject identity does not match its content')
    except (ValueError, TypeError) as exc:
        return {'status': 'UNKNOWN', 'reason': str(exc)[:500]}
    try:
        current = review_subject(root, project, work_id, basis, subject.get('request') or None)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return {'status': 'CHANGED', 'reason': str(exc).removeprefix('development_source: ')[:500]}
    if current['subject_id'] != subject['subject_id']:
        moved = [key for key in ('effects', 'changed_files', 'readonly_carry', 'stage', 'commission', 'latest_delta') if current.get(key) != subject.get(key)]
        return {'status': 'CHANGED', 'reason': 'the cumulative review subject moved: ' + ', '.join(moved or ['identity'])}
    return {'status': 'CURRENT', 'reason': 'every committed commission effect, current postimage and read-only carry pin still match'}


def subject_summary(subject):
    """Compact projection of a recorded subject: identity, counts and stage, never bodies or read claims."""
    if not isinstance(subject, dict):
        return None
    carry, stage = subject.get('readonly_carry') or {}, subject.get('stage') or {}
    return {'subject_id': subject.get('subject_id'), 'union': copy.deepcopy(subject.get('union')),
            'carry': {'source': carry.get('source'), 'digest': carry.get('digest')} if 'digest' in carry else {'state': carry.get('state')},
            'stage': stage.get('id') or stage.get('state'), 'latest_delta_effect_id': (subject.get('latest_delta') or {}).get('effect_id'),
            'geometry_states': sorted({row['geometry']['state'] for row in subject.get('changed_files') or ()}),
            'offered_not_observed': True, 'semantic_adequacy': 'UNASSESSED'}


# ------------------------------------------------------------------------------------------------ focused review input plan

def _reader_text(text):
    """Match the existing plain repository reader's universal-newline text units."""
    return text.replace('\r\n', '\n').replace('\r', '\n')


def _checked_edit_facts(item, text):
    """Verify retained facts against the pinned postimage AND reconstruct its dirty preimage.

    The Git base is deliberately irrelevant. Old/full candidates have no such proof.
    """
    facts = item.get('verified_edits')
    if not isinstance(facts, dict) or set(facts) != {'schema_version', 'before_sha256', 'after_sha256', 'before_chars', 'after_chars', 'edits'}:
        raise ValueError('VERIFIED_EDITS_UNAVAILABLE')
    if any(isinstance(facts[k], bool) or not isinstance(facts[k], int) or facts[k] < 0 for k in ('before_chars', 'after_chars')) \
            or facts['schema_version'] != VERIFIED_EDITS_SCHEMA or facts['before_sha256'] != item['before_sha256']             or facts['after_sha256'] != item['after_sha256'] or facts['after_chars'] != len(text):
        raise ValueError('VERIFIED_EDITS_INVALID')
    edits = facts['edits']
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_COMPACT_EDITS:
        raise ValueError('VERIFIED_EDITS_INVALID')
    chunks, after_offset, before_offset = [], 0, 0
    for index, edit in enumerate(edits):
        if not isinstance(edit, dict) or set(edit) != {'id', 'before', 'after'} or edit['id'] != 'edit-%d' % (index + 1):
            raise ValueError('VERIFIED_EDITS_INVALID')
        for span in (edit['before'], edit['after']):
            if not isinstance(span, dict) or set(span) != {'offset', 'chars', 'text'} or not isinstance(span['text'], str)                     or any(isinstance(span[k], bool) or not isinstance(span[k], int) or span[k] < 0 for k in ('offset', 'chars'))                     or len(span['text']) != span['chars']:
                raise ValueError('VERIFIED_EDITS_INVALID')
        before, after = edit['before'], edit['after']
        if not before['text'] or after['offset'] < after_offset or after['offset'] + after['chars'] > len(text)                 or text[after['offset']:after['offset'] + after['chars']] != after['text']:
            raise ValueError('VERIFIED_EDITS_INVALID')
        unchanged = text[after_offset:after['offset']]
        if before['offset'] != before_offset + len(unchanged):
            raise ValueError('VERIFIED_EDITS_INVALID')
        chunks.extend((unchanged, before['text']))
        before_offset = before['offset'] + before['chars']
        after_offset = after['offset'] + after['chars']
    chunks.append(text[after_offset:])
    original = ''.join(chunks)
    if len(original) != facts['before_chars'] or 'sha256:' + hashlib.sha256(original.encode('utf-8')).hexdigest() != facts['before_sha256']:
        raise ValueError('VERIFIED_EDITS_INVALID')
    for edit in edits:
        old = edit['before']
        if original.find(old['text']) != old['offset'] or original.find(old['text'], old['offset'] + 1) >= 0:
            raise ValueError('VERIFIED_EDITS_INVALID')
    return copy.deepcopy(facts)


def _plan_state(inputs):
    states = {item['state'] for item in inputs}
    return 'UNAVAILABLE' if 'UNAVAILABLE' in states else 'INCOMPLETE' if 'INCOMPLETE' in states else 'COMPLETE'


def _plan_read_handle(project, repository, path, expected, offset, limit):
    """Existing native repository read and qualified read-only Material HTTP projection."""
    from laplace.projects import library
    material = library.material_read_handle(project, {'view': 'preview',
        'target': {'owner': 'repository', 'repository': repository, 'path': path},
        'expected_sha256': expected, 'offset': offset, 'limit': limit})
    return {'operation': 'repository', 'payload': {'action': 'read', 'repository': repository,
        'path': path, 'expected_sha256': expected, 'offset': offset, 'limit': limit},
        'http': material['http'], 'human_read': material['human_read']}


def _plan_input(project, checkout, root, grant_row, repository, path, expected, candidate_file, windows, cumulative=None):
    target = _fenced(root, checkout, grant_row, path)
    row = {'path': path, 'sha256': expected, 'state': 'COMPLETE', 'reasons': [],
        'changed': bool(candidate_file and candidate_file['before_sha256'] != candidate_file['after_sha256']),
        'requested_context': copy.deepcopy(windows), 'verified_edits': None,
        'selected_context': [], 'initial_reads': [], 'uninspected_extents': [], 'uncovered_edit_ids': [],
        'fallback_read': _plan_read_handle(project, repository, path, expected, 0, REVIEW_PAGE_CHARS)}
    if cumulative is not None:
        # A commission change (any effect, any reissued grant) is a change of this input even when the latest
        # candidate never touched it; its geometry is the subject's retained-preimage -> current-postimage hunks.
        row.update(changed=True, cumulative_change=copy.deepcopy(cumulative), uncovered_hunk_ids=[])
    # Reuse the candidate owner's materialisation ceiling for this focused capability.
    # Whole-source authority/navigation remains available when geometry is unsupported.
    with target.open('rb') as stream:
        raw = stream.read(MAX_CANDIDATE_BYTES + 1)
    if len(raw) > MAX_CANDIDATE_BYTES:
        if _pin(target) != expected:
            raise ValueError('development_source: plan input changed while inspecting it.')
        row.update(state='UNAVAILABLE', reasons=['FOCUSED_GEOMETRY_EXCEEDS_CANDIDATE_BYTE_CEILING'],
            raw_bytes=target.stat().st_size, reader_chars=None, total_lines=None)
        return row
    if 'sha256:' + hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('development_source: plan input changed while inspecting it.')
    row['raw_bytes'] = len(raw)
    try:
        text = raw.decode('utf-8')
        if '\x00' in text or target.suffix.lower() == '.pdf':
            raise UnicodeError()
    except UnicodeError:
        row.update(state='UNAVAILABLE', reasons=['PLAIN_UTF8_GEOMETRY_UNAVAILABLE'], reader_chars=None, total_lines=None)
        return row
    reader = _reader_text(text)
    lines = reader.splitlines(keepends=True)
    starts, cursor = [], 0
    for line in lines:
        starts.append(cursor); cursor += len(line)
    row.update(reader_chars=len(reader), total_lines=len(lines))
    if candidate_file is not None:
        try:
            row['verified_edits'] = _checked_edit_facts(candidate_file, text)
        except (ValueError, KeyError, TypeError) as exc:
            row['reasons'].append(str(exc) if str(exc).startswith('VERIFIED_') else 'VERIFIED_EDITS_INVALID')
            row['state'] = 'UNAVAILABLE'
    extents = []
    for window in windows:
        start, end = window['line_start'], window['line_end']
        if end > len(lines):
            raise ValueError('development_source: a context window exceeds the pinned postimage lines: ' + path)
        a, b = starts[start - 1], starts[end - 1] + len(lines[end - 1])
        extents.append({'offset': a, 'end_offset': b, 'windows': [window['id']]})
    merged = []
    for extent in sorted(extents, key=lambda e: (e['offset'], e['end_offset'])):
        if merged and extent['offset'] < merged[-1]['end_offset']:
            merged[-1]['end_offset'] = max(merged[-1]['end_offset'], extent['end_offset'])
            merged[-1]['windows'].extend(extent['windows'])
        else:
            merged.append(copy.deepcopy(extent))
    facts = (row['verified_edits'] or {}).get('edits', [])
    for edit in facts:
        after = edit['after']
        a = len(_reader_text(text[:after['offset']]))
        b = len(_reader_text(text[:after['offset'] + after['chars']]))
        edit['reader_after'] = {'offset': a, 'chars': b - a}
        if reader and not any(e['offset'] <= a and b <= e['end_offset'] for e in merged):
            row['uncovered_edit_ids'].append(edit['id'])
    cursor = 0
    for extent in merged:
        a, b = extent['offset'], extent['end_offset']
        if a > cursor:
            row['uninspected_extents'].append({'offset': cursor, 'chars': a - cursor})
        extent.update(chars=b - a, covered_edit_ids=[e['id'] for e in facts
            if a <= e['reader_after']['offset'] and e['reader_after']['offset'] + e['reader_after']['chars'] <= b])
        row['selected_context'].append(extent)
        for offset in range(a, b, REVIEW_PAGE_CHARS):
            length = min(REVIEW_PAGE_CHARS, b - offset)
            row['initial_reads'].append({'path': path, 'offset': offset, 'chars': length,
                'stop_before_offset': b, 'read': _plan_read_handle(project, repository, path, expected, offset, length)})
        cursor = b
    if cursor < len(reader):
        row['uninspected_extents'].append({'offset': cursor, 'chars': len(reader) - cursor})
    if not reader:
        row['reasons'].append('EMPTY_INPUT_HAS_NO_LINE_WINDOW')
    if reader and not merged:
        row['reasons'].append('NO_SELECTED_CONTEXT')
    if row['uncovered_edit_ids']:
        row['reasons'].append('CHANGED_SPANS_OUTSIDE_SELECTED_CONTEXT')
    if cumulative is not None:
        if cumulative['geometry']['state'] != 'DERIVED':
            row['reasons'].append('CUMULATIVE_GEOMETRY_' + cumulative['geometry']['state'])
            row['state'] = 'UNAVAILABLE'
        spans = []
        for window in sorted(windows, key=lambda w: (w['line_start'], w['line_end'])):
            if spans and window['line_start'] <= spans[-1][1] + 1:
                spans[-1][1] = max(spans[-1][1], window['line_end'])
            else:
                spans.append([window['line_start'], window['line_end']])
        for hunk in cumulative['geometry']['hunks']:
            start, end = hunk['after_lines']
            if end < start:   # a pure deletion: the surviving neighbouring line anchors it
                start = end = max(1, min(start, len(lines)))
            if lines and not any(a <= start and end <= b for a, b in spans):
                row['uncovered_hunk_ids'].append(hunk['id'])
        if row['uncovered_hunk_ids']:
            row['reasons'].append('CUMULATIVE_CHANGES_OUTSIDE_SELECTED_CONTEXT')
    if row['reasons'] and row['state'] == 'COMPLETE':
        row['state'] = 'INCOMPLETE'
    return row


REVIEW_PREFLIGHT_SCHEMA = 'laplace.development-review-preflight/1'
REVIEW_SCAFFOLD_HEAD_LINES = 80
REVIEW_SCAFFOLD_EDIT_MARGIN = 6


def _preflight_windows(raw_windows, pins):
    windows = {path: [] for path in pins}
    for index, window in enumerate(raw_windows or []):
        if not isinstance(window, dict) or set(window) != {'path', 'line_start', 'line_end'} or window['path'] not in pins \
                or any(isinstance(window[k], bool) or not isinstance(window[k], int) or window[k] < 1 for k in ('line_start', 'line_end')) \
                or window['line_start'] > window['line_end']:
            raise ValueError('development_source: context windows name a covered input and inclusive positive line range.')
        windows[window['path']].append({'id': 'window-%d' % (index + 1), **window})
    return windows


def review_preflight(root: Path, project: str, payload: dict, door: dict) -> dict:
    """A BOUNDED pre-handoff diagnostic and an owner-derived window SCAFFOLD for one prospective Source review plan.

    Read-only. It reuses the exact plan geometry (_plan_input: current pins, verified edits of the selected candidate,
    the same window and coverage rules) over the named inputs and returns, per input, only state/reasons/lines/changed/
    uncovered edits, never bodies. The scaffold offers windows: every verified changed span with a margin, plus one
    coarse head window for an input that has no selected context. It is offered, NOT observed: it asserts no reading,
    waives no NO_SELECTED_CONTEXT, and a caller still chooses the contract/caller context it actually offers."""
    for key in ('work_id', 'grant_id', 'candidate_id'):
        if key not in payload:
            raise ValueError('development_source: review-preflight needs work_id, grant_id and candidate_id '
                             '(omitted paths default to the whole cumulative subject).')
    task, grant_row, checkout = _current(root, project, payload['grant_id'], 'read', door)
    if task['id'] != payload['work_id']:
        raise ValueError('development_source: the grant belongs to another Work.')
    cand = _latest(task, 'candidate', payload['candidate_id'])
    if cand is None or cand.get('grant_id') != grant_row['id']:
        raise ValueError('development_source: name a candidate of this grant.')
    selected, subject_check = None, None
    if 'source_subject' in payload:
        # The canonical admitted review subject, resolved ONCE with the resolver prepare_review_plan uses, so the offered
        # geometry and the arm's validation share one changed-file set: this commission's production plus any explicitly
        # selected prior production. A refused subject never falls back to a bare-commission scaffold.
        try:
            selected = review_subject(root, project, task['id'], {'grant_id': grant_row['id'], 'candidate_id': cand['id']}, payload['source_subject'])
            subject_check = {'state': 'ADMISSIBLE', 'summary': subject_summary(selected)}
        except ValueError as exc:
            subject_check = {'state': 'REFUSED', 'reason': str(exc).removeprefix('development_source: ')[:400]}
    if 'paths' in payload:
        paths, paths_origin = list(dict.fromkeys(payload['paths'])), 'CALLER'
    else:
        # Root causal case PHASE-7608dc0d: a producer naming only its latest candidate's files left 21 of 22 cumulative
        # inputs without context. Omitted paths mean the owner's whole subject: every declared obligation input, the
        # commission's committed production across reissued grants, and this candidate's files.
        _effects, derived = _commission_chains(task, {row['id'] for row in _commission_grants(task, grant_row)})
        declared = {path for row in task.get('review_obligations') or () for path in row.get('inputs') or ()}
        derived = set(derived) | {row['path'] for row in (selected or {}).get('changed_files') or ()}   # carry stays separate
        paths, paths_origin = sorted(declared | derived | {item['path'] for item in cand['files']}), 'CUMULATIVE_SUBJECT'
    if not paths or len(paths) > MAX_REVIEW_WINDOWS:
        raise ValueError('development_source: review-preflight names 1..%d inputs.' % MAX_REVIEW_WINDOWS)
    pins = {}
    for path in paths:
        pin = _pin(_fenced(root, checkout, grant_row, path))
        if pin is None:
            raise ValueError('development_source: review input %s is absent.' % path)
        pins[path] = pin
    supplied = (payload.get('source_context') or {}).get('windows') if isinstance(payload.get('source_context'), dict) else None
    if supplied is not None and len(supplied) > MAX_REVIEW_WINDOWS:
        raise ValueError('development_source: source_context has at most64 exact line windows.')
    windows = _preflight_windows(supplied, pins)
    files = {item['path']: item for item in cand['files']}
    inputs, scaffold = [], {}
    # The commission's whole committed production (reissued grants included), not only this candidate.
    commission_effects, chains = _commission_chains(task, {row['id'] for row in _commission_grants(task, grant_row)})
    cumulative, subject_problems = {}, []
    if selected is not None:
        # exactly the selected subject's retained-preimage -> current-postimage hunks, as prepare_review_plan derives them
        cumulative = {row['path']: _plan_cumulative(row) for row in selected['changed_files'] if row['path'] in pins}
    for path in (sorted(set(chains) & set(pins)) if selected is None else ()):
        try:
            cumulative[path] = _plan_cumulative(_cumulative_file(root, task, checkout, path, chains[path]))
        except ValueError as exc:
            subject_problems.append(str(exc).removeprefix('development_source: ')[:200])
    for path in sorted(pins):
        try:
            row = _plan_input(project, checkout, root, grant_row, grant_row['repository'], path, pins[path], files.get(path), windows[path],
                              cumulative.get(path))
        except ValueError as exc:
            inputs.append({'path': path, 'sha256': pins[path], 'state': 'INCOMPLETE', 'reasons': [str(exc).removeprefix('development_source: ')[:200]]})
            continue
        total = row.get('total_lines') or 0
        offered = [(w['line_start'], w['line_end']) for w in windows[path] if w['line_end'] <= total]
        if total and row['state'] != 'UNAVAILABLE':
            text = _reader_text(_fenced(root, checkout, grant_row, path).read_bytes().decode('utf-8'))
            for edit in (row.get('verified_edits') or {}).get('edits', []):
                span = edit.get('reader_after') or {}
                first = text.count('\n', 0, span.get('offset', 0)) + 1
                last = text.count('\n', 0, span.get('offset', 0) + span.get('chars', 0)) + 1
                offered.append((max(1, first - REVIEW_SCAFFOLD_EDIT_MARGIN), min(total, last + REVIEW_SCAFFOLD_EDIT_MARGIN)))
            for hunk in ((cumulative.get(path) or {}).get('geometry') or {}).get('hunks', []):
                start, end = hunk['after_lines']
                start = min(start, total)
                end = min(max(start, end), total)
                offered.append((max(1, start - REVIEW_SCAFFOLD_EDIT_MARGIN), min(total, end + REVIEW_SCAFFOLD_EDIT_MARGIN)))
            if not offered:
                offered.append((1, min(total, REVIEW_SCAFFOLD_HEAD_LINES)))
        merged = []
        for start, end in sorted(offered):
            if merged and start <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        scaffold[path] = merged
        inputs.append({'path': path, 'sha256': pins[path], 'state': row['state'], 'reasons': list(row['reasons']), 'total_lines': row.get('total_lines'),
                       'changed': row['changed'], 'uncovered_edit_ids': list(row['uncovered_edit_ids']),
                       'uncovered_hunk_ids': list(row.get('uncovered_hunk_ids') or []),
                       'cumulative_geometry': ((row.get('cumulative_change') or {}).get('geometry') or {}).get('state'),
                       'selected_windows': len(row['selected_context'])})
    # Fit the offered scaffold under the plan's window bound by collapsing a file's windows into one span, largest first.
    while sum(len(spans) for spans in scaffold.values()) > MAX_REVIEW_WINDOWS:
        path = max((p for p in scaffold if len(scaffold[p]) > 1), key=lambda p: len(scaffold[p]), default=None)
        if path is None:
            break
        scaffold[path] = [(scaffold[path][0][0], scaffold[path][-1][1])]
    offered_windows = [{'path': path, 'line_start': a, 'line_end': b} for path in sorted(scaffold) for a, b in scaffold[path]]
    refused = subject_check is not None and subject_check['state'] == 'REFUSED'
    if refused:
        offered_windows = []   # an explicit refused subject never offers usable commission-only windows; a legacy absent subject keeps them
    return {'schema_version': REVIEW_PREFLIGHT_SCHEMA, 'work_id': task['id'], 'grant_id': grant_row['id'], 'candidate_id': cand['id'],
            'state': 'UNAVAILABLE' if refused else _plan_state(inputs), 'paths_origin': paths_origin, 'pins': pins, 'inputs': inputs,
            'subject_geometry': 'REFUSED_SUBJECT' if refused else 'SELECTED_SUBJECT' if selected is not None else 'COMMISSION',
            'commission': {'effects': len(commission_effects), 'changed_total': len(chains), 'changed_paths': sorted(chains)[:64],
                           'problems': subject_problems,
                           'meaning': 'Committed commission production across reissued grants; the named candidate is one delta of it.'},
            'subject': subject_check,
            'incomplete': [row['path'] for row in inputs if row['state'] != 'COMPLETE'],
            'scaffold': {'windows': offered_windows, 'windows_total': len(offered_windows), 'within_bound': len(offered_windows) <= MAX_REVIEW_WINDOWS,
                         **({'withheld': 'REFUSED_SUBJECT: correct the selected source_subject; no commission-only windows are offered in its place.'} if refused else {}),
                         'offered_not_observed': True,
                         'meaning': 'Offered starting context only: verified changed spans with a margin and a coarse head window where no context was selected. '
                                    'It is not a read, a review or acceptance; replace head windows with the contract/caller context you actually offer.'}}


def prepare_review_plan(root: Path, project: str, work_id: str, basis: dict, pins: dict, source_context: dict, subject_request=None) -> dict:
    """Pure exact offered-input plan, never a read observation or semantic acceptance."""
    _review_pins(pins)
    observed = validate_review_basis(root, project, work_id, basis, consumed_pins=pins)
    if observed['status'] != 'CURRENT':
        raise ValueError('development_source: review plan source is ' + observed['status'] + ': ' + observed['reason'])
    if not isinstance(source_context, dict) or set(source_context) != {'windows'}             or not isinstance(source_context['windows'], list) or len(source_context['windows']) > MAX_REVIEW_WINDOWS:
        raise ValueError('development_source: source_context has at most64 exact line windows.')
    windows = {path: [] for path in pins}
    for index, window in enumerate(source_context['windows']):
        if not isinstance(window, dict) or set(window) != {'path', 'line_start', 'line_end'} or window['path'] not in pins                 or any(isinstance(window[k], bool) or not isinstance(window[k], int) or window[k] < 1 for k in ('line_start', 'line_end'))                 or window['line_start'] > window['line_end']:
            raise ValueError('development_source: context windows name a covered input and inclusive positive line range.')
        windows[window['path']].append({'id': 'window-%d' % (index + 1), **window})
    _task, grant_row, cand, _effect = _review_records(root, project, work_id,
        {key: basis[key] for key in ('grant_id', 'candidate_id')})
    checkout = Path(grant_row['checkout'])
    files = {item['path']: item for item in cand['files']}
    # The Source owner derives the whole cumulative subject from the same basis; the latest candidate stays its exact
    # anchor. The consumed inputs (<=64 obligation pins) are a bounded local projection of that subject.
    subject = review_subject(root, project, work_id, basis, subject_request)
    cumulative = {row['path']: _plan_cumulative(row) for row in subject['changed_files']}
    inputs = [_plan_input(project, checkout, root, grant_row, basis['repository'], path, expected, files.get(path), windows[path], cumulative.get(path))
              for path, expected in sorted(pins.items())]
    plan = {'schema_version': REVIEW_PLAN_SCHEMA_V2, 'source_identity': {k: v for k, v in basis.items() if k != 'pins'},
        'pins': dict(pins), 'source_context': copy.deepcopy(source_context), 'candidate_files': [
            {k: item[k] for k in ('path', 'before_sha256', 'after_sha256')} |
            {'changed': item['before_sha256'] != item['after_sha256'], 'verified_change_facts': 'verified_edits' in item}
            for item in cand['files']], 'inputs': inputs, 'state': _plan_state(inputs),
        'units': 'Repository Unicode characters after universal-newline decoding; raw-source SHA256 remains unchanged.',
        'semantic_adequacy': 'UNASSESSED', 'offered_not_observed': True,
        'read_rule': 'Use each exact bounded initial read. Never follow an EOF continuation beyond its stop_before_offset; expand deliberately with the same full raw pin.',
        'initial_read_calls': sum(len(item['initial_reads']) for item in inputs)}
    plan.update(review_subject=subject, latest_delta=copy.deepcopy(subject['latest_delta']),
                inputs_projection='The consumed inputs are a bounded local projection of review_subject; every subject path remains review scope.')
    plan['plan_id'] = 'DRP-' + _digest(plan)[7:]
    return copy.deepcopy(plan)


def review_plan_for_inputs(plan: dict, pins: dict) -> dict:
    """Pure immutable-plan projection; missing unrelated context cannot block another obligation."""
    _review_pins(pins)
    if not isinstance(plan, dict) or plan.get('schema_version') not in REVIEW_PLAN_SCHEMAS             or plan.get('plan_id') != 'DRP-' + _digest({k: v for k, v in plan.items() if k != 'plan_id'})[7:]:
        raise ValueError('development_source: recorded review plan identity is unavailable or changed.')
    if any(plan['pins'].get(path) != expected for path, expected in pins.items()):
        raise ValueError('development_source: plan consumption must be an identical subset of its pins.')
    selected = [item for item in plan['inputs'] if item['path'] in pins]
    if len(selected) != len(pins):
        raise ValueError('development_source: plan omits a consumed input.')
    return copy.deepcopy({'plan_id': plan['plan_id'], 'source_identity': plan['source_identity'], 'pins': dict(pins),
        'inputs': selected, 'candidate_files': [item for item in plan['candidate_files'] if item['path'] in pins],
        **({'review_subject': plan['review_subject'], 'latest_delta': plan['latest_delta']} if 'review_subject' in plan else {}),
        'outside_consumed_inputs': sorted(set(plan['pins']) - set(pins)), 'state': _plan_state(selected),
        'semantic_adequacy': 'UNASSESSED', 'offered_not_observed': True, 'read_rule': plan['read_rule'],
        'initial_read_calls': sum(len(item['initial_reads']) for item in selected)})


# ------------------------------------------------------------------------------------------------ isolated checks

def isolation_launcher() -> Path | None:
    found = shutil.which('bwrap')
    return Path(found).resolve() if found else None


_LAUNCHER_FEATURES: dict = {}


PRLIMIT = RUNTIME_MOUNT / 'bin' / 'prlimit'


def enforcement_available(launcher: Path | None) -> str | None:
    """None when every required enforcement exists; else the one reason the check is UNAVAILABLE before launch."""
    if launcher is None:
        return 'no isolation launcher (bwrap) on this host; a check is never run bare'
    try:
        import resource  # noqa: F401
    except ImportError:
        return 'no POSIX resource limits on this host'
    if not PRLIMIT.is_file():
        # the process budget (RLIMIT_NPROC) can only be applied INSIDE the new user namespace: applied before the launch
        # it is charged against the outer user's whole process count and the namespace creation itself fails
        return 'no %s on this host: the process budget cannot be applied inside the sandbox' % PRLIMIT
    for node in DEVICE_NODES:
        if not Path(node).exists():
            return 'device node %s is missing on this host; the read-only device directory cannot be composed' % node
    if str(launcher) not in _LAUNCHER_FEATURES:
        try:
            text = subprocess.run([str(launcher), '--help'], capture_output=True, text=True, timeout=10).stdout
        except Exception as exc:   # the launcher cannot even describe itself: fail closed
            return 'isolation launcher could not start: %s' % str(exc)[:200]
        _LAUNCHER_FEATURES[str(launcher)] = {'size': '--size' in text, 'die_with_parent': '--die-with-parent' in text, 'unshare_all': '--unshare-all' in text}
    features = _LAUNCHER_FEATURES[str(launcher)]
    missing = [name for name, present in features.items() if not present]
    return ('isolation launcher lacks %s' % ', '.join(missing)) if missing else None


#: the device nodes a check keeps (bound one by one with device semantics into a read-only device directory)
DEVICE_NODES = ('/dev/null', '/dev/zero', '/dev/urandom', '/dev/random')
#: the mounts the policy exposes, with the write authority each must show to a tiny attempt (regular file and directory creation)
POLICY_SURFACES = {'/': 'refused', '/dev': 'refused', str(RUNTIME_MOUNT): 'refused', '/proc': 'refused', 'stage': 'refused', str(SCRATCH): 'writable'}
_POLICY_PROBE = '''import json, os
def put(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
out = {}
for label, path in [("/", "/x"), ("/dev", "/dev/x"), (%(usr)r, %(usr)r + "/x"), ("/proc", "/proc/x"), ("stage", "x"), (%(tmp)r, %(tmp)r + "/x")]:
    try:
        put(path, b"x"); out[label] = "writable"
    except OSError:
        out[label] = "refused"
    try:
        os.mkdir(path + ".d"); out[label] = "writable"
    except OSError:
        pass
try:
    put("/dev/null", b"x"); out["device"] = "ok"
except OSError as e:
    out["device"] = "errno%%d" %% e.errno
try:
    for i in range(64):
        put(%(tmp)r + "/q%%d" %% i, b"x" * 1024)
    out["quota"] = "unbounded"
except OSError as e:
    out["quota"] = "enospc" if e.errno == 28 else "errno%%d" %% e.errno
out["cwd"] = os.getcwd()
try:
    with open(%(sentinel)r) as handle:
        out["sentinel"] = handle.read()
except OSError as e:
    out["sentinel"] = "errno%%d" %% e.errno
out["former_stage"] = "present" if os.path.lexists(%(old)r) else "absent"
out["mounts"] = sorted(line.split()[1] for line in open("/proc/self/mounts"))
print(json.dumps(out))
'''
#: The harmless known sentinel the policy probe's host side writes into the exact stage; the probe must read it relative to
#: the neutral working directory, and must NOT find the former absolute host stage inside the sandbox.
POLICY_SENTINEL_NAME = 'policy-sentinel.txt'
POLICY_SENTINEL = 'laplace neutral input sentinel\n'
_POLICY_VERIFIED: dict = {}


def mount_policy_problem(root: Path, launcher: Path) -> str | None:
    """The declared write policy, VERIFIED on this host once per process and launcher: a tiny attempt on every exposed mount
    (regular file and directory creation) must be refused everywhere but the bounded scratch, the device nodes must keep
    device semantics, and the scratch must reach ENOSPC; otherwise the check is UNAVAILABLE before any profile runs."""
    key = str(launcher)
    if key in _POLICY_VERIFIED:
        return _POLICY_VERIFIED[key]
    stage = (Path(root) / 'contract' / 'development_checks' / '.policy-probe' / str(os.getpid())).resolve()
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)
    profile = {'executable': str(RUNTIME_MOUNT / 'bin' / 'python3'), 'args': ['-I', '-c', _POLICY_PROBE % {
                   'usr': str(RUNTIME_MOUNT), 'tmp': str(SCRATCH), 'sentinel': POLICY_SENTINEL_NAME, 'old': str(stage)}],
               'timeout_s': 20, 'max_output_bytes': 65536, 'scratch_bytes': 2 * SCRATCH_PAGE, 'memory_bytes': 256 * 1024 ** 2, 'max_processes': 4}
    try:
        # fallible probe preparation stays inside the boundary: a failed write is a typed refusal and the stage is removed
        (stage / POLICY_SENTINEL_NAME).write_text(POLICY_SENTINEL)
        completed = subprocess.run(_isolation_argv(launcher, stage, profile), stdin=subprocess.DEVNULL, capture_output=True, timeout=30, cwd=str(stage),
                                   start_new_session=True, preexec_fn=_limits(profile))
        text = completed.stdout.decode('utf-8', errors='replace')
        observed = json.loads(text.strip().splitlines()[-1]) if completed.returncode == 0 and text.strip() else None
    except Exception as exc:
        observed, text = None, str(exc)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    if not observed:
        problem = 'the mount policy could not be verified: the probe did not run (%s)' % text.strip()[:300]
    else:
        wrong = {label: observed.get(label) for label, expected in POLICY_SURFACES.items() if observed.get(label) != expected}
        if observed.get('device') != 'ok':
            wrong['device'] = observed.get('device')
        if observed.get('quota') != 'enospc':
            wrong['quota'] = observed.get('quota')
        # the neutral input namespace: inputs readable at the fixed working directory, the former host stage absent
        if observed.get('cwd') != str(SANDBOX_INPUT):
            wrong['cwd'] = observed.get('cwd')
        if observed.get('sentinel') != POLICY_SENTINEL:
            wrong['sentinel'] = observed.get('sentinel')
        if observed.get('former_stage') != 'absent':
            wrong['former_stage'] = observed.get('former_stage')
        problem = ('the declared mount policy is not enforced on this host: ' + json.dumps(wrong, sort_keys=True)) if wrong else None
    if problem is None:
        _POLICY_VERIFIED[key] = None   # only a verified policy is remembered; a failed verification is asked again next time
    return problem


def _dependency_path(root: Path, checkout: Path, grant_paths, raw: str) -> Path:
    """One admitted READ-ONLY check dependency: checkout-relative without .., no symlink component, inside the checkout and
    outside every protected root, not git internals or credential-shaped, and NEVER a writable grant path (a writable file
    is a check input, so source authority never widens merely to make a check runnable)."""
    relative = Path(str(raw))
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise ValueError('development_source: dependency %s is not checkout-relative without ..' % raw)
    walk = checkout
    for part in relative.parts:
        walk = walk / part
        if walk.is_symlink():
            raise ValueError('development_source: dependency %s crosses a symlink; only real files are admitted.' % relative.as_posix())
    resolved = (checkout / relative).resolve()
    if not resolved.is_relative_to(checkout.resolve()):
        raise ValueError('development_source: dependency %s escapes the checkout.' % relative.as_posix())
    if any(resolved == protected or resolved.is_relative_to(protected) for protected in _protected_roots(root)):
        raise ValueError('development_source: dependency %s lies inside a protected root.' % relative.as_posix())
    if '.git' in relative.parts or relative.name in CREDENTIAL_NAMES or relative.suffix in CREDENTIAL_SUFFIXES:
        raise ValueError('development_source: dependency %s is git internals or credential-shaped.' % relative.as_posix())
    if any(fnmatch.fnmatchcase(relative.as_posix(), pattern) for pattern in grant_paths):
        raise ValueError('development_source: dependency %s is a writable grant path; name it as a check input, not a read-only dependency.' % relative.as_posix())
    return checkout / relative


def registered_runtime(root: Path) -> dict:
    """The serving root's REGISTERED lifecycle interpreter and its exact admission basis (laplace.core.runtime declaration
    runtime_profiles.toml#lifecycle.python). Never the LAPLACE_PYTHON override, a caller path or the candidate checkout.
    Its prefix (the resolved interpreter's bin/..) is mounted read-only; a prefix that is a filesystem root or contains the
    serving root or a protected root is refused because it would expose source."""
    from laplace.core import runtime as core_runtime
    serving = Path(root).resolve()
    try:
        profile = core_runtime.runtime_profile(serving)
    except core_runtime.RuntimePolicyError as exc:
        raise ValueError('development_source: no registered runtime is declared for this root: %s' % exc) from exc
    declared = Path(profile['python']).expanduser()
    selected = declared if declared.is_absolute() else serving / declared
    resolved = selected.resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ValueError('development_source: the registered runtime %s is not an executable file.' % selected)
    prefix = resolved.parent.parent
    exposed = [serving, *_protected_roots(serving)]
    if prefix == Path(prefix.anchor) or any(prefix == path or path.is_relative_to(prefix) for path in exposed):
        raise ValueError('development_source: the registered runtime prefix %s would expose the root or source; register a dedicated runtime.' % prefix)
    basis = {'schema_version': RUNTIME_ADMISSION_SCHEMA, 'kind': REGISTERED_RUNTIME, 'declaration': 'runtime_profiles.toml#lifecycle.python',
             'declared': profile['python'], 'expected_python': profile['expected_python'], 'executable': str(resolved),
             'prefix': str(prefix), 'executable_sha256': _pin(resolved)}
    return {**basis, 'identity': _digest(basis)}


#: The one manifest carrier shared by its two semantic roles: role -> (caller field path, label). Each role keeps its own
#: schema/repository/base/currentness rules in its own resolver; only the carrier shape and its diagnosis are shared.
MANIFEST_CARRIER_ROLES = {'check-dependency': ('checks.<name>.dependency_manifest', 'check dependency manifest'),
                          'review-carry': ('source_subject.carry', 'review carry manifest')}
MANIFEST_CARRIER_FORMS = ('inline {schema, members: [{path, sha256[, bytes]}]}',
                          'pinned project Artifact {artifact_id: "ART-...", expected_sha256}')


def manifest_carrier_shape(spec, role: str = 'check-dependency') -> dict | None:
    """None for a well-shaped carrier of either accepted form; otherwise ONE bounded, non-secret diagnostic naming the
    semantic role, field path, received keys, expected forms and correct coordinates. Shape only: it runs BEFORE any
    Artifact lookup and waives no member, pin, repository, base or fence rule; nothing is converted or invented."""
    field, label = MANIFEST_CARRIER_ROLES[role]
    keys = sorted(str(key) for key in spec)[:16] if isinstance(spec, dict) else None
    if isinstance(spec, dict):
        if 'members' in spec and 'artifact_id' not in spec:
            return None
        if set(spec) == {'artifact_id', 'expected_sha256'} and isinstance(spec['artifact_id'], str) and spec['artifact_id'].startswith('ART-') \
                and isinstance(spec['expected_sha256'], str):
            return None
    return {'role': role, 'label': label, 'field': field, 'received': type(spec).__name__, 'received_keys': keys,
            'expected': list(MANIFEST_CARRIER_FORMS),
            'coordinates': ('Members are repository-relative checkout paths with sha256 pins; a project Artifact carrier is named only by '
                            'artifact_id + expected_sha256. Work evidence rows (repository-relative {path, sha256}) and project Artifact '
                            'read paths are different coordinates and are never a carrier.')}


def _manifest_value(root: Path, project: str, spec, role: str = 'check-dependency') -> tuple:
    """One pinned manifest body: inline {schema, members} or a project Artifact {artifact_id, expected_sha256} whose exact
    bytes hold that JSON (the existing Artifact owner and file pins; no new store). Shared by the check dependency
    closure and the read-only review carry; neither grants write authority."""
    problem = manifest_carrier_shape(spec, role)
    if problem is not None:
        raise ValueError('development_source: the %s at %s is an inline manifest or a pinned Artifact reference; received %s with keys %s. '
                         'Expected %s. %s' % (problem['label'], problem['field'], problem['received'], problem['received_keys'],
                                              ' or '.join(problem['expected']), problem['coordinates']))
    if 'members' in spec:
        return spec, 'inline'
    ident, expected = spec.get('artifact_id'), str(spec.get('expected_sha256') or '')
    expected = 'sha256:' + expected.removeprefix('sha256:')
    from laplace.writing.records import _index
    from laplace.projects import artifacts
    record = _index.artifact_record(root, project, ident) if isinstance(ident, str) else None
    if record is None or record.get('scope', 'project') != 'project' or not isinstance(record.get('artifact_path'), str):
        raise ValueError('development_source: %s Artifact %s is not a project Artifact of %s.' % (MANIFEST_CARRIER_ROLES[role][1], ident, project))
    raw = artifacts.resolve_path(root, project, record['artifact_path']).read_bytes()
    if 'sha256:' + hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('development_source: %s Artifact %s does not have the stated bytes.' % (MANIFEST_CARRIER_ROLES[role][1], ident))
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise ValueError('development_source: %s Artifact %s is not JSON.' % (MANIFEST_CARRIER_ROLES[role][1], ident)) from exc
    return value, 'artifact:%s@%s' % (ident, expected)


def resolve_dependency_manifest(root: Path, project: str, checkout: Path, grant_paths, spec: dict, inline=None) -> dict:
    """Resolve and validate ONE pinned read-only dependency closure once (at grant). spec is an inline manifest
    {schema, members} or a project Artifact {artifact_id, expected_sha256} whose exact bytes hold that JSON (the existing
    Artifact owner and file pins; no new store). Every member must be unique, fenced by _dependency_path (no symlink,
    inside the checkout, not git/credential/protected, never a writable grant path), present and equal to its pin; an
    inline `dependencies` entry for the same path must carry the same pin. The member count and total bytes are bounded.
    Returns the immutable record the grant keeps: {schema, source, digest, members, members_total, bytes_total}."""
    value, source = _manifest_value(root, project, spec)
    members = value.get('members') if isinstance(value, dict) else None
    if not isinstance(value, dict) or value.get('schema') not in DEPENDENCY_MANIFEST_SCHEMAS or not isinstance(members, list) or not members:
        raise ValueError('development_source: a dependency manifest has schema %s and a nonempty members list.' % DEPENDENCY_MANIFEST_SCHEMA)
    if len(members) > MAX_DEPENDENCY_MANIFEST_MEMBERS:
        raise ValueError('development_source: dependency manifest has %d members, above the bound %d.' % (len(members), MAX_DEPENDENCY_MANIFEST_MEMBERS))
    pinned, total, problems = {}, 0, []
    for row in members:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str) or not isinstance(row.get('sha256'), str) or not _SHA.fullmatch(row['sha256']):
            raise ValueError('development_source: every dependency manifest member is {path, sha256:<64 hex>}.')
        relative = Path(row['path']).as_posix()
        if relative in pinned:
            raise ValueError('development_source: dependency manifest names %s twice.' % relative)
        if inline and relative in inline and inline[relative] != row['sha256']:
            raise ValueError('development_source: dependency %s has two different pins (inline and manifest).' % relative)
        try:
            path = _dependency_path(root, checkout, grant_paths, relative)
        except ValueError as exc:
            problems.append(str(exc).removeprefix('development_source: '))
            continue
        if not path.is_file():
            problems.append('member %s is missing' % relative)
            continue
        if _pin(path) != row['sha256']:
            problems.append('member %s differs from its pin' % relative)
            continue
        total += path.stat().st_size
        pinned[relative] = row['sha256']
    if problems:
        raise ValueError('development_source: dependency manifest refused (%d of %d members): %s' % (len(problems), len(members), '; '.join(problems[:8])))
    if total > MAX_DEPENDENCY_CLOSURE_BYTES:
        raise ValueError('development_source: dependency closure is %d bytes, above the bound %d.' % (total, MAX_DEPENDENCY_CLOSURE_BYTES))
    ordered = [{'path': path, 'sha256': pinned[path]} for path in sorted(pinned)]
    return {'schema': DEPENDENCY_MANIFEST_SCHEMA, 'source': source, 'digest': _digest(ordered), 'members': ordered,
            'members_total': len(ordered), 'bytes_total': total}


def _staged_mode(source: Path) -> int:
    """A staged input or dependency is read-only (0o444); a file the checkout marks executable stays executable (0o555),
    so a test that runs ./scripts/laplace-python inside the check is not refused EACCES (measured 2026-11-08 in node-suite:
    tests/build_cancellation.test.mjs and the PDF-only history pair test). The bytes and their sha256 pin are unchanged;
    nothing staged becomes writable."""
    return 0o555 if source.stat().st_mode & 0o111 else 0o444


def _stage_dependencies(root: Path, checkout: Path, grant_row: dict, profile: dict, stage: Path) -> tuple:
    """Validate the exact pinned read-only dependency closure BEFORE the profile runs and stage it read-only beside the
    inputs: the inline `dependencies` map and every member of the grant's recorded `dependency_manifest`. Every member
    must be present, real, unchanged and fenced, and the staged bytes stay within MAX_DEPENDENCY_CLOSURE_BYTES; any
    problem refuses the whole check (never a silent skip)."""
    pins, problems, staged_bytes = [], [], 0
    declared = [(relative, expected, 'read-only-dependency') for relative, expected in sorted((profile.get('dependencies') or {}).items())]
    inline = {relative for relative, _expected, _role in declared}
    declared += [(row['path'], row['sha256'], 'manifest-member') for row in ((profile.get('dependency_manifest') or {}).get('members') or [])
                 if row['path'] not in inline]
    for relative, expected, role in declared:
        try:
            source = _dependency_path(root, checkout, grant_row['paths'], relative)
        except ValueError as exc:
            problems.append(str(exc).removeprefix('development_source: '))
            continue
        if not source.is_file():
            problems.append('dependency %s is missing' % relative)
            continue
        target = stage / relative
        if target.exists():
            problems.append('dependency %s is also a staged check input' % relative)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        os.chmod(target, _staged_mode(source))
        staged = _pin(target)
        if staged != expected:
            problems.append('dependency %s differs from its granted pin' % relative)
            continue
        staged_bytes += target.stat().st_size
        if staged_bytes > MAX_DEPENDENCY_CLOSURE_BYTES:
            problems.append('the staged dependency closure exceeds %d bytes' % MAX_DEPENDENCY_CLOSURE_BYTES)
            break
        pins.append({'path': relative, 'sha256': staged, 'role': role})
    return pins, problems


def _isolation_argv(launcher: Path, stage: Path, profile: dict, runtime: dict | None = None) -> list[str]:
    """THE WHOLE WRITE POLICY (J-R3-R1-DEV): the root, the runtime mount, the staged inputs and the device directory are
    read-only mounts (the staged inputs at the fixed neutral SANDBOX_INPUT, also the working directory: the host stage
    path itself is never mounted, so a host-path guard, e.g. a protected Main prefix, never sees it inside the check); the device directory is a tmpfs holding only the bound device nodes (device semantics kept) and
    remounted read-only; /proc admits no regular files; the ONLY place a regular file or directory can be created is the
    size-bounded scratch tmpfs. Verified on the host by mount_policy_problem before any profile runs."""
    argv = [str(launcher), '--unshare-all', '--die-with-parent', '--new-session',
            '--ro-bind', str(RUNTIME_MOUNT), str(RUNTIME_MOUNT), '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64']
    prefix = Path(runtime['prefix']) if runtime else None
    extra = prefix is not None and not prefix.is_relative_to(RUNTIME_MOUNT)
    if extra:
        argv += ['--ro-bind', str(prefix), str(prefix)]   # the registered runtime: read-only, at its own absolute path
    argv += ['--proc', '/proc', '--tmpfs', '/dev']
    for node in DEVICE_NODES:
        argv += ['--dev-bind', node, node]
    argv += ['--symlink', '/proc/self/fd/0', '/dev/stdin', '--symlink', '/proc/self/fd/1', '/dev/stdout', '--symlink', '/proc/self/fd/2', '/dev/stderr',
             '--remount-ro', '/dev',
             # the ONLY writable place: a size-bounded isolated scratch filesystem; no host directory is mounted writable
             '--size', str(profile['scratch_bytes']), '--tmpfs', str(SCRATCH),
             '--ro-bind', str(stage), str(SANDBOX_INPUT), '--chdir', str(SANDBOX_INPUT), '--remount-ro', '/']
    return argv + [
            '--clearenv', '--setenv', 'PATH', (str(prefix / 'bin') + ':' if extra else '') + str(RUNTIME_MOUNT / 'bin'), '--setenv', 'HOME', str(SCRATCH),
            '--setenv', 'LAPLACE_CHECK_OUTPUT', str(SCRATCH), '--setenv', 'LAPLACE_CHECK_SCRATCH_BYTES', str(profile['scratch_bytes']),
            '--setenv', 'PYTHONDONTWRITEBYTECODE', '1', '--setenv', 'LC_ALL', 'C.UTF-8',
            # the budgets applied INSIDE the namespace (the process budget can only be charged there, see enforcement_available)
            '--', str(PRLIMIT), '--nproc=%d' % int(profile['max_processes']), '--as=%d' % int(profile['memory_bytes']),
            '--fsize=%d' % int(profile['scratch_bytes']), '--cpu=%d' % int(profile['timeout_s']), '--nofile=256',
            '--', runtime['executable'] if runtime else profile['executable'], *profile['args']]


def _limits(profile: dict):
    """The OS limits applied in the child before exec and inherited across bwrap (the process budget is applied inside,
    by prlimit in the argv: charged before the launch it would count the outer user's processes and fail the namespace)."""
    import resource

    def apply_limits():
        cpu = int(profile['timeout_s'])
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_AS, (int(profile['memory_bytes']), int(profile['memory_bytes'])))
        resource.setrlimit(resource.RLIMIT_FSIZE, (int(profile['scratch_bytes']), int(profile['scratch_bytes'])))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    return apply_limits


def _stage_inputs(root: Path, checkout: Path, grant_row: dict, profile: dict, stage: Path) -> list[dict]:
    """Materialise exactly the profile's inputs through the grant fence: pins recorded, nothing else of the checkout exists."""
    pins = []
    for pattern in profile['inputs']:
        matches = sorted(p for p in checkout.glob(pattern) if p.is_file())
        for path in matches:
            relative = path.relative_to(checkout).as_posix()
            try:
                fenced = _fenced(root, checkout, grant_row, relative)
            except ValueError:
                continue   # the fence decides what a check may read; a refused file is simply not staged
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fenced, target)
            os.chmod(target, _staged_mode(fenced))
            pins.append({'path': relative, 'sha256': _pin(target)})
    if not pins:
        raise ValueError('development_source: the check profile inputs matched no permitted file.')
    return pins


def _turn_control(root: Path, project: str, door: dict, grant_id: str):
    """The real cancellation path for a check: the acting turn's live job, its host's cancel marker, the grant's revocation and
    any change of the execution GENERATION the check joined (root, session, turn, host birth identity; read once here).
    A native actor's check is an auxiliary process of that generation (child_hosts._register_auxiliary_process), registered
    from whichever process runs this owner: a Claude native call runs in the provider's MCP adapter, not in the host.
    Returns (cancelled(), refusal(), register(process)); refusal() is the pre-launch ownership answer."""
    from laplace.work import project_work
    from laplace.writing import child_hosts, turn_jobs
    acting = _acting(root, project, door)
    session_id, turn_id = acting.get('session_id'), acting.get('turn_id')
    generation = child_hosts.auxiliary_generation(root, session_id, turn_id) if turn_id else None
    last = {'at': 0.0, 'revoked': False}
    owned = {}

    def stop_marked() -> bool:
        """The session's shared Stop marker (turn_control.interrupt_turn) applies to THIS generation only. Turn ids are
        unique and a turn is never re-hosted, so a marker naming another turn (an older generation, a dead host's) never
        stops this check. A marker naming the acting turn stops it: with this check's host, with no host (the remote
        branch's form), or with another host (ambiguous custody of the current turn: protective, as the dispatch, Work
        delivery and workflow consumers also read it by turn). An unreadable or malformed marker is protective."""
        path = child_hosts._host_path(root, session_id).with_suffix('.cancel.json')
        if not path.exists():
            return False
        marker = child_hosts._read_host(path)
        if not isinstance(marker.get('turn_id'), str) or not marker['turn_id']:
            return path.exists()   # present but malformed (or removed mid-read): protective while it exists
        return marker['turn_id'] == turn_id

    def cancelled() -> bool:
        if turn_id:
            job = turn_jobs._JOBS.get(turn_id)
            if job is not None and (job.get('interrupt_requested') or job.get('done')):
                return True
            if session_id and stop_marked():
                return True
            if generation is not None and child_hosts.auxiliary_problem(root, generation):
                return True
            if owned and child_hosts.auxiliary_stop_requested(root, generation, owned['entry']):
                return True   # a selected-turn Stop from the host process marked (and terminated) this exact check
        if time.monotonic() - last['at'] > 0.5:   # the ledger is read at most twice a second
            last['at'] = time.monotonic()
            for task in project_work._tasks(project, root).values():
                row = _latest(task, 'grant', grant_id)
                if row is not None:
                    last['revoked'] = row.get('state') != 'ACTIVE'
        return last['revoked']

    def refusal() -> str | None:
        if not turn_id:
            return None   # the human door: the calling thread owns its process
        if generation is None:
            return 'the acting turn %s has no live hosted execution to own the check' % turn_id
        return child_hosts.auxiliary_problem(root, generation)

    def register(process) -> None:
        if not turn_id:
            return
        reason = refusal()
        if reason:
            raise ValueError(reason)
        _current(root, project, grant_id, 'check', door)   # the grant and its commission still stand at ownership
        owned['entry'] = child_hosts._register_auxiliary_process(root, generation, process, 'development-check')

    def stopped() -> bool:
        """A selected-turn Stop marked THIS registered check (it may have ended the process before the loop looked)."""
        return bool(owned) and child_hosts.auxiliary_stop_requested(root, generation, owned['entry'])
    return cancelled, refusal, register, stopped


#: After the launcher exits, how long the owner waits for its killed process group to be reaped before retaining the stage.
STAGE_SETTLE_S = 2.0


def _settle_stage(stage: Path, process=None) -> dict:
    """Owned cleanup of one check's staged inputs on EVERY terminal path (Root sequence 8). The stage is removed only after
    actual process proof: no process was launched, or the launcher has exited and signal 0 finds no member of its process
    group (start_new_session made the group). A live or unprovable process keeps the stage and says why; a removal error
    is reported and the stage retained, never ignored. stdout, results, pins and diagnostics live outside the stage."""
    if process is None:
        proof = 'no check process was launched'
    elif process.poll() is None:
        return {'state': 'RETAINED', 'reason': 'the check launcher has not exited; the stage stays until it is proved gone'}
    else:
        settle_by = time.monotonic() + STAGE_SETTLE_S
        while True:
            try:
                os.killpg(process.pid, 0)
                alive = 'a member of the check process group is still alive'
            except ProcessLookupError:
                alive = None
            except OSError as exc:
                alive = 'the check process group could not be proved empty: %s' % str(exc)[:200]
            if alive is None or time.monotonic() > settle_by:
                break
            time.sleep(0.05)
        if alive:
            return {'state': 'RETAINED', 'reason': alive + '; the stage stays until it is proved gone'}
        proof = 'the launcher exited (%s) and its process group is empty' % process.returncode
    if not stage.exists():
        return {'state': 'ABSENT', 'proof': proof}
    try:
        shutil.rmtree(stage)
    except OSError as exc:
        return {'state': 'FAILED', 'proof': proof, 'error': str(exc)[:300], 'retained': stage.exists()}
    if stage.exists():
        return {'state': 'FAILED', 'proof': proof, 'error': 'the stage still exists after removal', 'retained': True}
    return {'state': 'REMOVED', 'proof': proof}


def _finish_check(root: Path, row: dict, launched: dict) -> None:
    """Every terminal check path retains its row through here, once: the stage is settled first, so the durable row
    carries the explicit stage_cleanup outcome instead of an ignored removal."""
    from laplace.work import project_work
    if launched.get('stage') is not None and 'stage_cleanup' not in row:
        row['stage_cleanup'] = _settle_stage(launched['stage'], launched.get('process'))
    launched['appended'] = True
    project_work._append(root, row)


def check(root: Path, project: str, payload: dict, door: dict) -> dict:
    """The one check entrance. An owned finally settles the stage on every terminal path, including an owner error raised
    after staging: a still-running launcher is first killed by process group and waited, then settled with proof, and
    the row is retained with its outcome before the error propagates."""
    launched: dict = {}
    try:
        return _check(root, project, payload, door, launched)
    finally:
        if launched.get('stage') is not None and not launched.get('appended'):
            process = launched.get('process')
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            row = launched.get('row')
            if row is None:
                _settle_stage(launched['stage'], process)
            else:
                if not row.get('state'):
                    row.update(state='FAILED' if process is not None else 'REFUSED',
                               reason='the check stopped on an owner error before it settled' + ('' if process is not None else '; nothing ran'))
                _finish_check(root, row, launched)


def _check(root: Path, project: str, payload: dict, door: dict, launched: dict) -> dict:
    from laplace.work import project_work
    _require(payload, 'check')
    task, grant_row, checkout = _current(root, project, payload['grant_id'], 'check', door)
    profile = (grant_row.get('checks') or {}).get(payload['name'])
    if profile is None:
        raise ValueError('development_source: the grant names no check profile %r.' % payload['name'])
    targets = _check_targets(root, checkout, grant_row, payload['name'], profile, payload.get('targets'))
    ident = 'DK-' + _digest({'grant': grant_row['id'], 'name': payload['name'], 'ts': _now()})[7:31]
    output = (Path(root) / 'contract' / 'development_checks' / ident).resolve()
    stage = output / 'input'
    stage.mkdir(parents=True, exist_ok=True)
    launched['stage'] = stage
    row = {'record': RECORD, 'kind': KINDS['check'], 'id': ident, 'work_id': task['id'], 'project': project, 'grant_id': grant_row['id'],
           'name': payload['name'], 'base': grant_row['base'], 'output_root': str(output), 'ts': _now(), 'actor': _actor(root, project, payload, door),
           'budgets': {key: profile[key] for key in ('timeout_s', 'max_output_bytes', 'scratch_bytes', 'memory_bytes', 'max_processes')},
           'scratch': {'bytes': profile['scratch_bytes'], 'page_bytes': SCRATCH_PAGE, 'granularity': 'whole pages; every file consumes at least one page; ENOSPC at the bound during execution'},
           **({'targets': targets} if targets else {})}

    launched['row'] = row

    def unavailable(reason):
        row.update(state='UNAVAILABLE', reason=reason)
        _finish_check(root, row, launched)
        return {'ok': False, 'check': _public_check(row)}
    launcher = isolation_launcher()
    reason = enforcement_available(launcher) or mount_policy_problem(root, launcher)
    if reason:
        return unavailable(reason)
    cancelled, refusal, register, stopped = _turn_control(root, project, door, grant_row['id'])
    if cancelled():
        row.update(state='CANCELLED', reason='the acting turn was already interrupted, its host gone or the grant revoked')
        _finish_check(root, row, launched)
        return {'ok': False, 'check': _public_check(row)}
    row['inputs'] = _stage_inputs(root, checkout, grant_row, profile, stage)
    staged = {item['path']: item['sha256'] for item in row['inputs']}
    drift = [path for path, expected in profile.get('fixed_inputs', {}).items() if staged.get(path) != expected]
    if drift:
        row.update(state='REFUSED', reason='fixed check input changed or was not staged: ' + ', '.join(drift))
        _finish_check(root, row, launched)
        return {'ok': False, 'check': _public_check(row)}
    runtime = None
    if profile.get('runtime', 'system') == REGISTERED_RUNTIME:
        admitted = profile.get('runtime_admission') or {}
        try:
            runtime = registered_runtime(root)
            problem = None if runtime['identity'] == admitted.get('identity') else (
                'the registered runtime changed since the grant (granted %s, now %s)' % (str(admitted.get('identity'))[:19], runtime['identity'][:19]))
        except (ValueError, OSError) as exc:
            problem = 'the registered runtime is unavailable: %s' % str(exc)[:200]
        if problem:
            row.update(state='REFUSED', reason=problem + '; recovery: the human door re-grants against the current runtime registration. Nothing ran.')
            _finish_check(root, row, launched)
            return {'ok': False, 'check': _public_check(row)}
        row['runtime'] = {key: runtime[key] for key in ('kind', 'identity', 'executable', 'prefix', 'expected_python')}
    stage_started = time.perf_counter()
    dependencies, problems = _stage_dependencies(root, checkout, grant_row, profile, stage)
    closure = profile.get('dependency_manifest')
    if closure:
        members = [item for item in dependencies if item['role'] == 'manifest-member']
        row['dependency_closure'] = {'schema': closure['schema'], 'source': closure['source'], 'digest': closure['digest'],
            'members_total': closure['members_total'], 'staged_members': len(members),
            'staged_bytes': sum((stage / item['path']).stat().st_size for item in members if (stage / item['path']).is_file()),
            'stage_ms': int((time.perf_counter() - stage_started) * 1000), 'problems': problems[:16], 'problems_total': len(problems),
            'coverage': 'COMPLETE' if not problems and len(members) == closure['members_total'] else 'INCOMPLETE'}
        dependencies = [item for item in dependencies if item['role'] != 'manifest-member']
    if problems:
        row.update(state='REFUSED', reason='read-only check dependency refused: ' + '; '.join(problems)[:600]
                   + '; recovery: restore the exact pinned bytes or have the human door re-grant the exact current closure. Nothing ran.')
        _finish_check(root, row, launched)
        return {'ok': False, 'check': _public_check(row)}
    if dependencies:
        row['dependencies'] = dependencies
    if payload.get('candidate_id'):
        cand = _latest(task, 'candidate', payload['candidate_id'])
        if cand is None:
            raise ValueError('development_source: unknown candidate %s.' % payload['candidate_id'])
        staged = {item['path']: item['sha256'] for item in row['inputs']}
        drift = [f['path'] for f in cand['files'] if staged.get(f['path']) != f['after_sha256']]
        if drift:
            row.update(state='REFUSED', reason='staged inputs differ from the candidate postimages: ' + ', '.join(drift))
            _finish_check(root, row, launched)
            return {'ok': False, 'check': _public_check(row)}
        row['candidate_id'] = payload['candidate_id']
    argv = _isolation_argv(launcher, stage, {**profile, 'args': [*profile['args'], *targets]}, runtime)
    row['isolation'] = {'launcher': str(launcher), 'argv_sha256': hashlib.sha256(json.dumps(argv).encode()).hexdigest(),
                        'namespaces': 'unshare-all',
                        # where the inputs are INSIDE the sandbox, distinct from the retained host custody (output_root/input)
                        'input_mount': {'sandbox_path': str(SANDBOX_INPUT), 'cwd': str(SANDBOX_INPUT), 'host_stage': str(stage),
                                        'meaning': 'The exact verified host stage is bound read-only at sandbox_path, also the working '
                                                   'directory; the host stage path is not mounted inside the sandbox. host_stage and '
                                                   'output_root are host custody coordinates, not sandbox paths.'},
                        'read_only': ['/', str(RUNTIME_MOUNT),
                                      *([runtime['prefix'] + ' (registered runtime)'] if runtime and not Path(runtime['prefix']).is_relative_to(RUNTIME_MOUNT) else []),
                                      str(SANDBOX_INPUT) + (' (inputs and %d pinned read-only dependencies)' % len(dependencies) if dependencies else ''), '/dev (tmpfs remounted read-only; device nodes %s bound with device semantics)' % ', '.join(DEVICE_NODES), '/proc'],
                        'writable': ['%s (isolated tmpfs, %d bytes; no host mount)' % (SCRATCH, profile['scratch_bytes'])], 'policy_verified': True,
                        'published': ['stdout (at most %d bytes)' % profile['max_output_bytes']],
                        'rlimits': ['RLIMIT_CPU', 'RLIMIT_AS', 'RLIMIT_FSIZE', 'RLIMIT_NOFILE', 'RLIMIT_NPROC'],
                        'environment': ['PATH', 'HOME', 'LAPLACE_CHECK_OUTPUT', 'LAPLACE_CHECK_SCRATCH_BYTES', 'PYTHONDONTWRITEBYTECODE', 'LC_ALL']}
    owner = refusal()
    if owner or cancelled():
        row.update(state='CANCELLED', reason='no live owner for the check before launch: %s' % (owner or 'the acting turn was interrupted or the grant revoked'))
        _finish_check(root, row, launched)
        return {'ok': False, 'check': _public_check(row)}
    started = time.perf_counter()
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
                                   cwd=str(output), preexec_fn=_limits(profile))
    except Exception as exc:
        return unavailable('isolation launcher could not start: %s' % str(exc)[:300])
    launched['process'] = process
    try:
        register(process)
    except Exception as exc:   # the host refused to own the process (cancelled or no longer this turn): stop it now
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        process.wait()
        row.update(state='CANCELLED', reason='the child host refused ownership: %s' % str(exc)[:200])
        _finish_check(root, row, launched)
        return {'ok': False, 'check': _public_check(row)}
    collected, truncated, limit = bytearray(), threading.Event(), profile['max_output_bytes']

    def pump():
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                return
            if len(collected) + len(chunk) > limit:
                collected.extend(chunk[:max(0, limit - len(collected))]); truncated.set()
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
                return
            collected.extend(chunk)
    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    deadline = started + profile['timeout_s']
    state = None
    while process.poll() is None:
        if cancelled():
            state = 'CANCELLED'
        elif time.perf_counter() > deadline:
            state = 'TIMEOUT'
        if state:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            break
        time.sleep(0.05)
    process.wait()
    reader.join(timeout=5)
    wall_ms = int((time.perf_counter() - started) * 1000)
    text = bytes(collected)
    if state is None:
        if stopped() or process.returncode != 0 and cancelled():
            state = 'CANCELLED'   # an owner Stop terminated the registered process (the launcher's own exit code may be 0)
        elif truncated.is_set():
            state = 'FAILED'
        elif process.returncode == 0:
            state = 'COMPLETE'
        elif process.returncode == 1 and text.lstrip().startswith(b'bwrap:'):
            state = 'UNAVAILABLE'
        else:
            state = 'FAILED'
    # the owner's bounded publication: the scratch died with the namespace; only the capped stdout is retained on the host
    (output / 'stdout.txt').write_bytes(text)
    row.update(state=state, exit_code=process.returncode, wall_ms=wall_ms, stdout_bytes=len(text), truncated=truncated.is_set(), retained_bytes=len(text),
               stdout_tail=text[-TAIL_BYTES:].decode('utf-8', errors='replace'), stdout_sha256='sha256:' + hashlib.sha256(text).hexdigest(),
               **_failing(profile.get('failures'), text, truncated.is_set() or state == 'TIMEOUT', profile.get('sandbox_differences') or ()),
               **({'reason': 'the isolation launcher refused before the profile ran: ' + text[:300].decode('utf-8', errors='replace')} if state == 'UNAVAILABLE' else {}))
    _finish_check(root, row, launched)
    return {'ok': state == 'COMPLETE', 'check': _public_check(row)}


def _public_check(row: dict) -> dict:
    public = _public_check_fields(row)
    if row.get('stdout_sha256') and row.get('project') and row.get('work_id'):
        # The owner-issued scoped read of the retained bytes; output_root stays a recorded location, never a capability.
        public['output_read'] = output_handle(row['project'], row['work_id'], row['id'], row['stdout_sha256'])
    return public


def _public_check_fields(row: dict) -> dict:
    return {key: row.get(key) for key in ('id', 'grant_id', 'candidate_id', 'name', 'state', 'exit_code', 'wall_ms', 'stdout_bytes', 'truncated', 'retained_bytes',
                                          'stdout_tail', 'stdout_sha256', 'output_root', 'reason', 'inputs', 'dependencies', 'dependency_closure', 'runtime', 'isolation', 'budgets', 'scratch', 'stage_cleanup', 'ts')} | \
        {key: row[key] for key in ('targets', 'failing', 'failing_total', 'failing_complete', 'sandbox_differences') if key in row}


def _check_targets(root: Path, checkout: Path, grant_row: dict, name: str, profile: dict, raw) -> list:
    """The files a check names after the profile's fixed argv: each a real permitted file of the checkout (the grant fence)
    matching one of the profile's declared targets globs. Nothing else is ever appended."""
    globs = profile.get('targets') or ()
    if raw is None:
        if profile.get('requires_targets'):
            raise ValueError('development_source: check %s names the files to run in targets (matching %s).' % (name, ', '.join(globs)))
        return []
    if not globs:
        raise ValueError('development_source: check %s takes no targets; its argv is fixed.' % name)
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_CHECK_TARGETS or not all(isinstance(item, str) and item for item in raw):
        raise ValueError('development_source: targets is a list of 1-%d checkout-relative file names.' % MAX_CHECK_TARGETS)
    targets = []
    for item in raw:
        relative = Path(item).as_posix()
        if not any(fnmatch.fnmatchcase(relative, pattern) for pattern in globs):
            raise ValueError('development_source: target %s does not match check %s targets %s.' % (relative, name, ', '.join(globs)))
        if not _fenced(root, checkout, grant_row, relative).is_file():
            raise ValueError('development_source: target %s is not a file in the checkout.' % relative)
        if relative not in targets:
            targets.append(relative)
    return targets


_TAP_FAILURE = re.compile(r'^(\s*)not ok \d+ - (.+?)\s*(?:#\s*(\w+).*)?$', re.M)
_PYTEST_FAILURE = re.compile(r'^(?:FAILED|ERROR) (\S+)', re.M)


def _failing(parser, raw: bytes, cut: bool, declared=()) -> dict:
    """Failing test names read from the runner's own output by the profile's declared parser; never inferred. TAP: every
    'not ok' line that is not a TODO or SKIP directive, innermost first as the runner printed them; pytest: the FAILED and
    ERROR node ids of its summary. failing_complete is false when the output was cut (truncated or timed out). The
    profile's declared sandbox_differences are repeated with failed true or false against every name of this run."""
    if parser not in FAILURE_PARSERS:
        return {}
    text = raw.decode('utf-8', errors='replace')
    if parser == 'tap':
        names = [match.group(2) for match in _TAP_FAILURE.finditer(text) if (match.group(3) or '').upper() not in ('TODO', 'SKIP')]
    else:
        names = _PYTEST_FAILURE.findall(text)
    unique = list(dict.fromkeys(names))
    found = set(unique)
    return {'failing': unique[:MAX_FAILING_NAMES], 'failing_total': len(unique), 'failing_complete': not cut,
            **({'sandbox_differences': [{'name': item['name'], 'cause': item['cause'], 'failed': item['name'] in found} for item in declared]} if declared else {})}


OUTPUT_SCHEMA = 'laplace.development-check-output/1'
#: JSON-escaped content budget of ONE output page (the encoded string, not raw bytes): the whole native/HTTP envelope
#: with its handles, receipts and context stays inside the project's 30,000-byte delivery line. No cap is raised.
OUTPUT_PAGE_JSON_BYTES = 12000
TERMINAL_CHECK_STATES = ('COMPLETE', 'FAILED', 'TIMEOUT', 'CANCELLED', 'UNAVAILABLE', 'REFUSED')


def output_handle(project, work_id, check_id, stdout_sha256, offset=0) -> dict:
    """The ONE exact read of a retained check stdout page; the check row, each page and every refusal issue it."""
    payload = {'action': 'status', 'work_id': work_id, 'check_id': check_id, 'expected_sha256': stdout_sha256, 'offset': offset}
    return {'operation': 'development_source', 'payload': payload,
            'http': {'method': 'POST', 'url': '/work/development', 'payload': {'project': project, **payload}}}


def _utf8_boundary(raw, end, floor):
    while floor < end < len(raw) and (raw[end] & 0xC0) == 0x80:
        end -= 1
    return end


def output(root: Path, project: str, payload: dict, door: dict) -> dict:
    """ONE scoped page of a terminal check's RETAINED stdout (Root goal item 3).

    Bound to this project's Work and its recorded check row, pinned to the recorded stdout_sha256, paged in raw retained
    bytes that never split a UTF-8 sequence, and sized by the JSON-escaped content so the whole envelope stays bounded.
    It reads only the owner's recorded output folder: no live grant, write authority or stage is needed, so a terminal
    result stays readable after stage removal or grant expiry. Refusals are STRUCTURED (_view_refusal): a stale pin,
    a past-end offset or a split UTF-8 offset issue the exact same-record restart; changed, purged or missing bytes are
    UNAVAILABLE with the recorded hash, truncation and custody and no recovery; an unknown or foreign identity discloses
    nothing. Current bytes never substitute an old pin, and a producer-capped output stays explicitly truncated. Reading executes and records nothing."""
    from laplace.work import project_work
    for key in ('work_id', 'check_id', 'expected_sha256'):
        if key not in payload:
            raise ValueError('development_source: the retained-output status view needs work_id, check_id and expected_sha256 '
                             '(the recorded stdout_sha256).')
    task = project_work._tasks(project, root).get(payload['work_id'])
    row = None if task is None else next((item for item in _latest_per_id(rows(task, 'check')) if item.get('id') == payload['check_id']), None)
    if row is None:
        # unknown and foreign identities are indistinguishable: nothing about another record is disclosed or issued
        raise ValueError('development_source: no retained check output with these identities is recorded on a Work of this project '
                         '(unknown or foreign); nothing is disclosed and no read is issued.')
    recorded = row.get('stdout_sha256')
    if row.get('state') not in TERMINAL_CHECK_STATES or not recorded:
        raise _view_refusal('development_source: check %s (%s) has no retained terminal stdout yet.' % (row['id'], row.get('state')),
                            project, task['id'], code='NOT_TERMINAL', field='check_id', observed=row.get('state'),
                            reinspect={'operation': 'development_source', 'payload': {'action': 'status', 'work_id': task['id']}})
    pin = str(payload['expected_sha256'])
    expected = pin if pin.startswith('sha256:') else 'sha256:' + pin
    restart = output_handle(project, task['id'], row['id'], recorded)
    if expected != recorded:
        raise _view_refusal('development_source: the pin does not match the recorded stdout of check %s; restart_read is the exact '
                            'read of its recorded bytes.' % row['id'], project, task['id'], code='STALE_PIN', field='expected_sha256',
                            expected=expected, observed=recorded, restart=restart)
    custody = {'check_id': row['id'], 'stdout_sha256': recorded, 'retained_bytes': row.get('retained_bytes'),
               'producer_output_truncated': bool(row.get('truncated')), 'output_root': row.get('output_root'),
               'stage_cleanup': copy.deepcopy(row.get('stage_cleanup'))}

    def unavailable(why, observed=None):
        return _view_refusal('development_source: check %s retained stdout is UNAVAILABLE (%s). No current bytes substitute the '
                             'recorded %s and no read recovers it.' % (row['id'], why, recorded), project, task['id'], code='UNAVAILABLE',
                             field='stdout', expected=recorded, observed=observed, state='UNAVAILABLE', recovery=None, custody=custody)
    base = (Path(root) / 'contract' / 'development_checks').resolve()
    folder = (base / row['id']).resolve()
    if folder.parent != base or (row.get('output_root') and Path(row['output_root']).resolve() != folder):
        raise unavailable('its output location is not the owner-recorded folder; nothing was read')
    try:
        raw = (folder / 'stdout.txt').read_bytes()
    except FileNotFoundError:
        raise unavailable('no longer retained: purged or missing') from None
    observed = 'sha256:' + hashlib.sha256(raw).hexdigest()
    if observed != recorded:
        raise unavailable('its bytes changed since they were recorded', observed)
    offset = payload.get('offset', 0)
    if offset > len(raw):
        raise _view_refusal('development_source: offset %d is beyond the %d retained stdout bytes of check %s.' % (offset, len(raw), row['id']),
                            project, task['id'], code='PAST_END', field='offset', expected=len(raw), observed=offset, restart=restart)
    if offset < len(raw) and (raw[offset] & 0xC0) == 0x80:
        raise _view_refusal('development_source: offset %d splits a UTF-8 sequence of check %s stdout; use an issued page offset.'
                            % (offset, row['id']), project, task['id'], code='UTF8_BOUNDARY', field='offset', observed=offset, restart=restart)
    end = min(len(raw), offset + OUTPUT_PAGE_JSON_BYTES)
    while True:
        end = _utf8_boundary(raw, end, offset)
        if end == offset and offset < len(raw):   # one sequence wider than the walk: take it whole, never an empty NEXT
            end = min(len(raw), offset + 4)
        text = raw[offset:end].decode('utf-8', errors='replace')
        if len(json.dumps(text).encode('utf-8')) <= OUTPUT_PAGE_JSON_BYTES or end - offset <= 4:
            break
        end = offset + max(4, (end - offset) * 3 // 4)
    # The shared delivery owner's planned line (writing.delivery: declared bound minus receipts, envelope and reserved late
    # additions) bounds the WHOLE emitted page as the native doors serialize it; no post-publication clipping.
    from laplace.writing import delivery
    line = delivery.owner_line()
    page = _output_page(project, task, row, raw, recorded, restart, offset, end)
    while line is not None and end - offset > 4 and delivery.emitted(page) > line:
        end = _utf8_boundary(raw, offset + max(4, (end - offset) * 3 // 4), offset)
        page = _output_page(project, task, row, raw, recorded, restart, offset, end)
    delivery.record_projection('output', {'check_id': row['id'], 'offset': offset, 'end_offset': end})
    return page


def delivery_profile(payload):
    """writing.delivery.PROFILE_OWNERS: the retained-output status view is bounded to the shared navigation line; every
    other development_source act keeps its declared contract."""
    if isinstance(payload, dict) and payload.get('action') == 'status':
        from laplace.work import project_work_navigation as nav
        return {'bound': nav.CAP, 'owner': 'development_source.output' if 'check_id' in payload else
                'development_source.row' if 'row_id' in payload else 'development_source.status'}
    return None


def _output_page(project, task, row, raw, recorded, restart, offset, end):
    text = raw[offset:end].decode('utf-8', errors='replace')
    try:
        raw[offset:end].decode('utf-8')
        lossy = False
    except UnicodeDecodeError:
        lossy = True
    return {'schema_version': OUTPUT_SCHEMA, 'work_id': task['id'], 'check_id': row['id'], 'grant_id': row.get('grant_id'),
            'name': row.get('name'), 'state': row.get('state'), 'exit_code': row.get('exit_code'),
            'stdout_sha256': recorded, 'retained_bytes': len(raw), 'producer_output_truncated': bool(row.get('truncated')),
            'units': 'raw retained stdout bytes; page offsets never split a UTF-8 sequence',
            'offset': offset, 'end_offset': end, 'content': text, 'encoding': 'UTF-8_WITH_REPLACEMENT' if lossy else 'UTF-8',
            'eof': end == len(raw),
            'page_read': output_handle(project, task['id'], row['id'], recorded, offset),
            'next_read': output_handle(project, task['id'], row['id'], recorded, end) if end < len(raw) else None,
            'restart_read': restart, 'stage_cleanup': copy.deepcopy(row.get('stage_cleanup')),
            'authority': ('Historical retained output of a recorded check: reading it executes nothing, needs no live grant or write '
                          'authority, and is neither a current check nor acceptance.'),
            'truncation': ('The producer output reached the profile cap; only these retained bytes exist and the rest is not recoverable.'
                           if row.get('truncated') else None)}


#: What a status read does NOT say (Root goal item 4); returned with every status so a reader never infers authority or
#: idleness from a recorded label or a zero count.
# ------------------------------------------------------------------------------------------------ the lane (wave 13)

def check_profiles(root: Path) -> dict:
    """The fixed check profiles a lane grant carries (profiles/development_checks.json, incorporation D6): each entry's
    profile is exactly the grant's check-profile shape; copied_from names the existing profile its limits came from."""
    path = Path(root) / CHECK_PROFILES
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('development_source: the check profiles %s cannot be read: %s' % (CHECK_PROFILES, str(exc)[:200])) from exc
    if value.get('schema') != CHECK_PROFILES_SCHEMA or not isinstance(value.get('profiles'), dict) or not value['profiles']:
        raise ValueError('development_source: %s is not a %s document with profiles.' % (CHECK_PROFILES, CHECK_PROFILES_SCHEMA))
    return value


def _lane_profiles(root: Path) -> tuple[dict, list]:
    """(checks, withheld): every declared profile this root can admit; a registered-python profile on a root that declares
    no registered runtime is withheld with the owner's reason, never granted against another interpreter."""
    checks, withheld = {}, []
    for name, entry in check_profiles(root)['profiles'].items():
        profile = copy.deepcopy(entry['profile'])
        if profile.get('runtime', 'system') == REGISTERED_RUNTIME:
            try:
                registered_runtime(root)
            except ValueError as exc:
                withheld.append({'name': name, 'reason': str(exc)[:300]})
                continue
        checks[name] = profile
    return checks, withheld


def _lane_dependencies(root: Path, checkout: Path, checks: dict, withheld: list) -> None:
    """Pin each profile's lane_dependencies (profiles/development_checks.json: files a check reads outside the writable lane
    paths) from the cut lane into that grant profile's existing dependencies {path: sha256} map, which the grant validates
    and every check re-pins before staging. A profile whose dependency the lane lacks is withheld with the owner's reason."""
    entries = check_profiles(root)['profiles']
    for name in list(checks):
        pins, problem = {}, None
        for relative in entries[name].get('lane_dependencies') or ():
            try:
                pins[relative] = _pin(_dependency_path(root, checkout, LANE_PATHS, relative))
            except (OSError, ValueError) as exc:
                problem = str(exc).removeprefix('development_source: ')
            if problem is None and pins[relative] is None:
                problem = 'its read-only dependency %s is not in the lane' % relative
            if problem:
                break
        if problem:
            withheld.append({'name': name, 'reason': problem[:300]})
            del checks[name]
        elif pins:
            checks[name]['dependencies'] = {**checks[name].get('dependencies', {}), **pins}


def _git(source: Path, *args, timeout: int = 60) -> subprocess.CompletedProcess:
    git = shutil.which('git')
    if not git:
        raise ValueError('development_source: git is not available on this host.')
    return subprocess.run([git, '-C', str(source), *args], capture_output=True, text=True, timeout=timeout)


def _tree_bytes(path: Path) -> int:
    total = 0
    for folder, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != '.git']
        for name in files:
            try:
                total += (Path(folder) / name).lstat().st_size
            except OSError:
                pass
    return total


def _public_lane(task: dict, row: dict | None) -> dict | None:
    if row is None:
        return None
    held = [grant for grant in _latest_per_id(rows(task, 'grant')) if grant.get('repository') == row['id']]
    # the lane's grant as its own row states it: the newest ACTIVE one, else the newest (a discarded lane's grant is REVOKED)
    current = ([grant for grant in held if grant.get('state') == 'ACTIVE'] or held or [None])[-1]
    return {key: copy.deepcopy(row[key]) for key in ('id', 'state', 'work_id', 'checkout', 'base', 'branch', 'cut_at', 'ts', 'expires_at', 'bytes',
                                                      'parent_session_id', 'profiles_withheld', 'discarded_at', 'removal', 'revoked_grants') if key in row} | \
        {'grants': [grant['id'] for grant in held],
         'grant': None if current is None else {key: copy.deepcopy(current.get(key)) for key in ('id', 'state', 'paths', 'operations', 'parent_session_id', 'expires_at', 'revoked_at')}}


def lane(root: Path, project: str, payload: dict, door: dict) -> dict:
    """Cut a lean worktree of the serving checkout at its HEAD (scripts/sparse_worktree.sh ... lean) under lane_home()/<work-id>,
    append the Work's development-lane row and grant it to the parent session: src/**, tests/**, scripts/**, profiles/**,
    every operation, the fixed check profiles, the lane's lifetime and no evaluator. Human door only; one ACTIVE lane per Work
    (a repeat answers the existing lane). The lane path passes the protected-root refusal before anything is cut."""
    from laplace.core import checkout as serving
    from laplace.work import project_work
    _require(payload, 'lane')
    if door.get('origin') != 'human':
        raise ValueError('development_source: a lane is cut only through the human/admin owner boundary (POST /work/development).')
    parent = str(payload['parent_session_id'])
    _author_session(root, project, parent, 'parent_session_id')
    work_id = str(payload['work_id'])
    lifetime = int(payload.get('lifetime_s') or LANE_LIFETIME_S)
    if not 60 <= lifetime <= MAX_LIFETIME_S:
        raise ValueError('development_source: a lane lifetime is between 60 s and %d s.' % MAX_LIFETIME_S)

    def current_task():
        task = project_work._tasks(project, root).get(work_id)
        if task is None:
            raise ValueError('development_source: name an existing Work id of this project.')
        if payload['expected_work_revision'] != project_work._task_revision(task):
            raise project_work.WorkConflict('Read the exact Work before cutting a lane.', project, task['id'],
                                            expected=payload['expected_work_revision'], observed=project_work._task_revision(task), field='expected_work_revision')
        return task
    task = current_task()
    existing = lane_row(task)
    if existing is not None and existing['state'] == 'ACTIVE':
        return {'ok': True, 'reused': True, 'lane': _public_lane(task, existing)}
    checks, withheld = _lane_profiles(root)
    source = serving.source_tree().resolve()   # the app's own source checkout (in the live app also its root)
    base = _base(source)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    name = re.sub(r'[^A-Za-z0-9._-]', '-', work_id)
    checkout = lane_home() / name
    branch = 'app-dev/%s-%s' % (name, stamp)
    _refuse_protected(root, checkout)
    if checkout.exists():
        raise ValueError('development_source: %s already exists; it is not a lane this Work holds. Remove it or discard its lane first.' % checkout)
    script, bash = source / LANE_SCRIPT, shutil.which('bash')
    if not script.is_file() or not bash:
        raise ValueError('development_source: the lane cutter %s (or bash) is not available in the serving checkout.' % LANE_SCRIPT)
    checkout.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        cut_run = subprocess.run([bash, str(script), str(checkout), base, branch, 'lean'], cwd=str(source), capture_output=True, text=True, timeout=LANE_CUT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        cut_run = None
    if cut_run is None or cut_run.returncode != 0 or not checkout.is_dir():
        _remove_lane({'checkout': str(checkout), 'branch': branch, 'base': base, 'source_checkout': str(source)})
        raise ValueError('development_source: the lane could not be cut: %s' % ('timed out after %d s' % LANE_CUT_TIMEOUT_S if cut_run is None
                         else (cut_run.stderr or cut_run.stdout or 'exit %d' % cut_run.returncode).strip()[-400:]))
    cut_ms = int((time.perf_counter() - started) * 1000)
    _lane_dependencies(root, checkout, checks, withheld)
    now = time.time()
    row = {'record': RECORD, 'kind': KINDS['lane'], 'id': LANE_PREFIX + work_id, 'work_id': work_id, 'project': project, 'state': 'ACTIVE',
           'checkout': str(checkout.resolve()), 'base': base, 'branch': branch, 'source_checkout': str(source), 'cut_at': _now(), 'ts': _now(),
           'expires_at': dt.datetime.fromtimestamp(now + lifetime, dt.timezone.utc).isoformat(), 'bytes': _tree_bytes(checkout), 'cut_ms': cut_ms,
           'parent_session_id': parent, 'profiles_withheld': withheld, 'actor': _actor(root, project, payload, door)}
    try:
        with project_work.dispatch_lock(root):
            task = current_task()
            raced = lane_row(task)
            if raced is not None and raced['state'] == 'ACTIVE':
                raise ValueError('development_source: another lane of this Work became ACTIVE while this one was cut.')
            project_work._append(root, row)
        granted = _issue(root, project, {'request_id': 'lane-%s-%s' % (stamp, _digest(work_id)[7:19]), 'work_id': work_id,
                                         'expected_work_revision': payload['expected_work_revision'], 'repository': row['id'], 'parent_session_id': parent,
                                         'paths': list(LANE_PATHS), 'operations': list(OPERATIONS), 'checks': checks, 'lifetime_s': lifetime}, door)
    except Exception as exc:
        removal = _remove_lane(row)
        if any(item.get('id') == row['id'] and item.get('branch') == branch for item in rows(project_work._tasks(project, root).get(work_id) or {}, 'lane')):
            with project_work.dispatch_lock(root):
                project_work._append(root, {**row, 'state': 'DISCARDED', 'ts': _now(), 'discarded_at': _now(), 'removal': removal,
                                            'reason': 'the lane grant was refused: %s' % str(exc)[:300]})
        raise
    task = project_work._tasks(project, root)[work_id]
    return {'ok': True, 'lane': _public_lane(task, lane_row(task)), 'grant': granted['grant'],
            'read': {'operation': 'development_source', 'payload': {'action': 'status', 'work_id': work_id, 'session_id': parent}}}


def _remove_lane(row: dict) -> dict:
    """Remove a lane worktree and, when it holds no commit of its own, its branch. The outcome is reported, never assumed."""
    source, checkout, branch = Path(row['source_checkout']), Path(row['checkout']), row.get('branch')
    outcome = {}
    try:
        if checkout.exists():
            done = _git(source, 'worktree', 'remove', '--force', str(checkout))
            outcome['worktree'] = 'REMOVED' if done.returncode == 0 and not checkout.exists() else 'FAILED'
            if outcome['worktree'] == 'FAILED':
                outcome['error'] = (done.stderr or done.stdout or 'the worktree still exists').strip()[-300:]
        else:
            _git(source, 'worktree', 'prune')
            outcome['worktree'] = 'ABSENT'
        if branch:
            tip = _git(source, 'rev-parse', '--verify', '--quiet', 'refs/heads/' + branch)
            if tip.returncode != 0:
                outcome['branch'] = 'ABSENT'
            elif tip.stdout.strip() == row.get('base'):
                outcome['branch'] = 'REMOVED' if _git(source, 'branch', '-D', branch).returncode == 0 else 'KEPT'
            else:
                outcome['branch'] = 'KEPT'
                outcome['branch_reason'] = 'the branch holds commits of its own'
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        outcome.setdefault('worktree', 'FAILED')
        outcome['error'] = str(exc)[:300]
    return outcome


def discard(root: Path, project: str, payload: dict, door: dict) -> dict:
    """Discard the Work's ACTIVE lane named by its branch: every ACTIVE grant on it is revoked, the worktree removed, and the
    lane row appended DISCARDED with the removal outcome. Human door only; an older branch is refused, never discarded."""
    from laplace.work import project_work
    _require(payload, 'discard')
    if door.get('origin') != 'human':
        raise ValueError('development_source: a lane is discarded only through the human/admin owner boundary (POST /work/development).')
    with project_work.dispatch_lock(root):
        task = project_work._tasks(project, root).get(str(payload['work_id']))
        if task is None:
            raise ValueError('development_source: name an existing Work id of this project.')
        row = lane_row(task)
        if row is None:
            raise ValueError('development_source: Work %s has no lane.' % task['id'])
        if row.get('branch') != payload['branch']:
            raise ValueError('development_source: the lane of Work %s is now %s, not %s; read the Work again before discarding.' % (task['id'], row.get('branch'), payload['branch']))
        if row['state'] != 'ACTIVE':
            return {'ok': True, 'already': row['state'], 'lane': _public_lane(task, row)}
        actor = _actor(root, project, payload, door)
        revoked = []
        for grant_row in _latest_per_id(rows(task, 'grant')):
            if grant_row.get('repository') == row['id'] and grant_row.get('state') == 'ACTIVE':
                project_work._append(root, {**grant_row, 'state': 'REVOKED', 'revoked_at': _now(), 'reason': 'lane discarded', 'revoked_by': actor})
                revoked.append(grant_row['id'])
        final = {**row, 'state': 'DISCARDED', 'ts': _now(), 'discarded_at': _now(), 'revoked_grants': revoked, 'removal': _remove_lane(row), 'discarded_by': actor}
        project_work._append(root, final)
    task = project_work._tasks(project, root)[task['id']]
    return {'ok': True, 'lane': _public_lane(task, lane_row(task))}


def _offers(root: Path, project: str, task: dict, session_id: str) -> list:
    """What the human door offers for this Work as seen from one session: cut a lane when none is ACTIVE, discard the ACTIVE
    lane, and run each check profile of every ACTIVE grant this session holds. Each offer carries its exact request."""
    from laplace.work import project_work
    offers = []
    row = lane_row(task)
    if row is None or row['state'] != 'ACTIVE':
        try:
            _author_session(root, project, session_id, 'session_id')
            offers.append({'action': 'lane', 'request': {'action': 'lane', 'work_id': task['id'], 'expected_work_revision': project_work._task_revision(task),
                                                          'parent_session_id': session_id}})
        except ValueError as exc:
            offers.append({'action': 'lane', 'request': None, 'refused': str(exc)})
    else:
        offers.append({'action': 'discard', 'request': {'action': 'discard', 'work_id': task['id'], 'branch': row['branch']}})
    for grant_row in _latest_per_id(rows(task, 'grant')):
        if grant_row.get('state') != 'ACTIVE' or grant_row.get('parent_session_id') != session_id or 'check' not in (grant_row.get('operations') or ()):
            continue
        for name, profile in sorted((grant_row.get('checks') or {}).items()):
            offers.append({'action': 'check', 'grant_id': grant_row['id'], 'repository': grant_row.get('repository'), 'name': name,
                           'request': {'action': 'check', 'grant_id': grant_row['id'], 'name': name},
                           'targets': {'globs': list(profile['targets']), 'required': bool(profile.get('requires_targets'))} if profile.get('targets') else None})
    return offers


STATUS_NOTES = (
    'A recorded grant state ACTIVE is the ledger row, not current admissibility: every read, candidate, apply and check '
    're-resolves the Work scope, base, lifetime, paths and commission and can still refuse.',
    'A native allowance account with active 0 means no admitted native invocation is open on that account; it is not '
    'proof that the provider process or session is idle.',
)


# ------------------------------------------------------------------------------------------------ the one door

def handle(root: Path, project: str, payload: dict, door: dict) -> dict:
    from laplace.core import admission
    admission.admit_owner_payload('development_source', payload, contract(), project=project)
    action = payload.get('action')
    if action == 'grant':
        return grant(root, project, payload, door)
    if action == 'delegate':
        return delegate(root, project, payload, door)
    if action == 'revoke':
        return revoke(root, project, payload, door)
    if action == 'arm':
        from laplace.work import project_work_continuity
        return project_work_continuity.arm(root, project, payload, door)
    if action == 'proof':
        from laplace.work import project_work_continuity
        return project_work_continuity.attach_proof(root, project, payload, door)
    if action == 'read':
        return read(root, project, payload, door)
    if action == 'status' and 'check_id' in payload:
        # The retained-output VIEW of the existing status read: same read action, same common native read classification.
        return output(root, project, payload, door)
    if action == 'status' and ('row_id' in payload or 'part' in payload):
        # The exact paged detail of one NOT_EXPANDED status row (its issued detail_read).
        return row_detail(root, project, payload, door)
    if action == 'status':
        # notes and live allowance metadata are part of the one fitted page (status/_fitted)
        return status(root, project, payload, door)
    if action == 'candidate':
        return candidate(root, project, payload, door)
    if action == 'apply':
        return apply(root, project, payload, door)
    if action == 'check':
        return check(root, project, payload, door)
    if action == 'review-preflight':
        return review_preflight(root, project, payload, door)
    if action == 'lane':
        return lane(root, project, payload, door)
    if action == 'discard':
        return discard(root, project, payload, door)
    raise ValueError('development_source action is grant, delegate, revoke, read, status, candidate, apply, check, arm, proof, lane or discard.')
