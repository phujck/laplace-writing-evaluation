"""Versioned operating knowledge derived from the deployed writing contracts.

The brief is regenerated for each turn. Tool schema identity is separate from
project/profile identity, so content updates do not unnecessarily discard a
provider thread, while an obsolete native tool declaration cannot be resumed.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from laplace.projects.writing_sources import CODE_MODE_IMAGE_GUIDANCE, PROJECT_RESPONSE_GUIDANCE

VERSION = 'laplace.writing-operating-brief/1'
NATIVE_REGISTRATION_VERSION = 'laplace.native-writing-registration/1'
_LEGACY_CALLBACK_PROTOCOL_V1 = 'laplace-project-tool-call/1'
CURRENT_CALLBACK_PROTOCOL = 'laplace-project-tool-call/1'
# Client-executed project tools belong to this writer connection. Codex workers
# do not inherit them, so this surface must not advertise native delegation.  App Server
# dynamic tools are additive to its native surface: `web_search='disabled'` is the installed
# protocol's explicit control, not an inference from an omitted key. Native local read tools
# remain, and inherited/global MCP may remain; read-only does not govern external MCP effects.
CODEX_SESSION_CONFIG = {'features.multi_agent': False, 'project_doc_max_bytes': 0,
                        'web_search': 'disabled'}
# Stable installed feature controls that can expose network-capable or externally-mutating
# native/app/plugin tools beside dynamicTools. They are process controls as well as thread
# policy: inherited MCP names are resolved separately from effective startup metadata.
CODEX_PROCESS_DISABLED_FEATURES = (
    'apps', 'plugins', 'browser_use', 'browser_use_external',
    'browser_use_full_cdp_access', 'computer_use',
    'in_app_browser', 'remote_plugin', 'plugin_sharing', 'image_generation')
CODEX_MCP_SERVERS_MAX = 256
CODEX_MCP_STATUS_PAGES_MAX = 8
SESSION_POLICY_VERSION = 'laplace.writing-session-policy/2'
USAGE_FACTS_VERSION = 'laplace.provider-usage-facts/1'
DELIVERY_RECEIPT_VERSION = 'laplace.provider-delivery/1'
# Single source vocabulary; collectors and read projections use this declaration.
USAGE_FACTS_CONTRACT = {
    'schema_version': USAGE_FACTS_VERSION,
    'counter_scopes': ['last_request', 'logical_turn', 'binding_cumulative', 'context_snapshot', 'unknown'],
    'phases': ['stream', 'terminal', 'fallback'],
    'counter_domains': ['main_conversation', 'provider_auxiliary', 'provider_all', 'unknown'],
    'counts': ['input', 'cached_input', 'cache_write_input', 'output', 'reasoning_output', 'total'],
    'selection_keys': ['context_snapshot', 'logical_turn', 'binding_cumulative', 'unselected_variants'],
    'reasoning_is_subset_of_output': True,
    'absent_count': None,
    'raw_custody': 'contract/writing_bodies',
    'legacy': 'unchanged; basis unknown unless explicitly recorded',
}
# Only typed counter/identity metadata enters raw custody. Nested free text is excluded.
USAGE_RAW_COUNTS = frozenset(('inputTokens','cachedInputTokens','cacheWriteInputTokens','outputTokens','reasoningOutputTokens','totalTokens',
    'input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens','total_tokens',
    'cache_read_input_tokens','cache_creation_input_tokens','cacheReadInputTokens','cacheCreationInputTokens','thinkingTokens',
    'contextWindow','maxOutputTokens','duration_ms','duration_api_ms','num_turns'))
USAGE_RAW_IDENTITIES = frozenset(('costBasis','canonicalModel','provider','service_tier','speed','inference_geo'))
USAGE_RAW_COSTS = frozenset(('costUSD','total_cost_usd'))
USAGE_RAW_NESTED_COUNTS = {
    'output_tokens_details': frozenset(('thinking_tokens','reasoning_tokens')),
    'cache_creation': frozenset(('ephemeral_5m_input_tokens','ephemeral_1h_input_tokens')),
    'server_tool_use': frozenset(('web_search_requests','web_fetch_requests')),
}
USAGE_CONTEXT_PROXY_METRIC = 'last_request_input_proxy'
USAGE_FRESH_BINDING_BASIS = 'codex.fresh_binding_cumulative'
DELIVERY_RECEIPT_CONTRACT = {
    'schema_version': DELIVERY_RECEIPT_VERSION,
    'states': ['PREPARED', 'SENT', 'OBSERVED', 'UNOBSERVABLE', 'WITHHELD'],
    'parts': ['kernel', 'body', 'frame', 'task'],
    'fingerprints': 'UTF-8 sha256 and byte length; canonical tool alias for semantic identity',
    'requested_controls_are_inventory_proof': False,
} 
# The ONE door, and the name each transport's session actually sees.  The Claude CLI
# namespaces every MCP tool as mcp__<server>__<tool>, so a brief that says
# "use laplace_project" names a tool that session cannot see.
DOOR_TOOL = 'laplace_project'
CLAUDE_TOOL_PREFIX = 'mcp__laplace__'
TOOL_VISIBLE_NAME = {'claude': CLAUDE_TOOL_PREFIX + DOOR_TOOL, 'codex': DOOR_TOOL}
# The instruction bytes, in two parts, because one transport rebuilds its system slot on
# every process and the other holds immutable thread instructions set once.  KERNEL is
# session-invariant; BODY is this project's current state and is delivered once.
KERNEL_MEMBERS = ['schema_version', 'tool_contract_digest', 'shared_rules_revision',
                  'capability_guidance_revision', 'project', 'provider_session_policy',
                  'rules', 'orientation_layers', 'capability_guidance', 'tool_visible_name']
# The TURN's own frame.  These four are mode-dependent, and one session changes mode: the
# corpus's third session runs discuss, discuss, discuss, work, revise on one thread.  While
# they were session instructions, the Claude transport delivered the new mode on its next
# process (the CLI rebuilds its system prompt) and the Codex thread kept the mode it started
# with, which `orientation_delta` does not carry either.  They ride with every turn now, on
# both transports, so neither session can be working in a mode it was not told about.
FRAME_MEMBERS = ['mode', 'role', 'permissions', 'scoped_permissions', 'response_contract']
BODY_MEMBERS = ['writing_style', 'architecture_prior', 'presentation', 'project_protocol', 'source_repositories']
# Brief keys the instructions never carry: full contracts stay reachable through help and
# the audit receipt, and the current target belongs to the turn, not to the session.
INSTRUCTIONS_OMIT = {'operation_contract', 'operation_payload_contracts', 'workspace',
                     'selected_source', 'live_scope', 'digest', 'exact_action_digests',
                     'action_catalogue_digest', 'role_permissions_digest',
                     'native_registration_signature'}
KERNEL_HEADER = 'LAPLACE OPERATING BRIEF — CURRENT DEPLOYED CONTRACT'
FRAME_HEADER = 'LAPLACE OPERATING BRIEF — THIS TURN\'S MODE AND PERMISSIONS'
BODY_HEADER = 'LAPLACE OPERATING BRIEF — PROJECT STATE, DELIVERED ONCE FOR THIS SESSION'
BLOCK_JOIN = '\n\n'
# The ONE delta channel.  A resumed session is told once, in one block, in the one channel
# both transports carry verbatim, what this conversation already holds and what moved since
# its last turn.  There were two blocks and two grammars for that one question: the brief's
# `CHANGED PROJECT ORIENTATION SINCE THE LAST TURN` (digests that moved) and the delivery's
# `ALREADY DELIVERED IN THIS CONVERSATION` (parts withheld, each naming its read), with the
# project body silently withheld on a resume and named by neither.
DELTA_HEADER = 'WHAT THIS CONVERSATION WAS ALREADY GIVEN, AND WHAT CHANGED SINCE YOUR LAST TURN'
DELTA_PROSE = (
    '`already_delivered` names what you were given earlier in THIS conversation and whose '
    'source token has not moved, so it is not repeated. It is a delivery receipt, not proof '
    'that provider-owned compaction retained the exact bytes. Each row names the declared '
    'read that returns current content. `changed` carries only the project guidance whose '
    'digest moved; guidance absent from it is unchanged and still binding.')
# The read that returns each member of the project body the session is given once.  The
# body is withheld on every resumed process (`instructions.body.on_resume`), so the delta
# names it with the same per-part grammar the delivery's withheld parts use.
BODY_READS = {
    'writing_style': {'operation': 'writing_style', 'payload': {}},
    'architecture_prior': {'operation': 'structure', 'payload': {'view': 'architecture-profile'}},
    # `document`, not `style`: `style` is a WRITE (writing_tools.py:750 lists its views)
    # and is not in `writing_tools.READS` at all, so the row promised a read the session
    # cannot make.  The document read is the one that returns the presentation views
    # (`authoring_surface.py:1498` maps it to {document, presentation}).
    'presentation': {'operation': 'document', 'payload': {}},
    'project_protocol': {'operation': 'project_guidance', 'payload': {}},
    'source_repositories': {'operation': 'repository', 'payload': {'action': 'list'}},
}
# The three door operations that reach the network.  Nothing outside the door does.
NETWORK_DOOR_OPERATIONS = ['literature_discover', 'literature_lookup', 'reference_fetch']
# Compatibility counts have seven names; usage_basis states their actual scope.
USAGE_PROJECTION = ['input', 'cached_input', 'cache_write_input', 'output',
                    'reasoning_output', 'total', 'context_window']
TURN_OUTPUT_REQUIRED = ['status', 'native_id', 'text', 'error', 'turn_id', 'resolved_model']
TURN_OUTPUT_OPTIONAL = ['proposal', 'usage', 'usage_basis', 'usage_facts', 'delivery_receipt', 'context_tokens_used',
                        'context_window_advertised', 'context_window_effective',
                        'native_file_changes', 'provider_issues', 'provider_stage']
TURN_STATUS_VALUES = ['completed', 'failed', 'interrupted']
# The one failure row's shape.  `provider` and `tool_use_id` ride on every row and are null
# where the transport has no such id: a CLI tool call has one, a Codex item/tool/call is
# identified by its turn, and that id is the only link from a banked permission denial to
# the provider's own call.
FAILURE_ROW_FIELDS = ['record', 'id', 'ts', 'project', 'turn_id', 'operation', 'payload',
                      'error_type', 'error', 'provider', 'tool_use_id', 'next_reads', 'recovery']
FAILURE_OPERATION_CHARS_MAX = 160
# The payload's bound is the SEAM's, not a character ceiling of this contract's own.  The
# row goes through `authoring_surface._bank`, which holds `writing-tool-failure.payload` by
# reference at any size (`_CUSTODY_ALWAYS`), so the request is bounded in the row AND
# recoverable in full -- which a 16,000-character truncation to {truncated, sha256, preview}
# was not.  Declaring the mechanism rather than a number keeps one bound, named once.
FAILURE_PAYLOAD_BOUND = 'custody-reference:contract/writing_bodies'
# Capacity and compaction belong to the provider on both transports.  A catalogue maximum
# is useful labelled telemetry, but it is not the active session's effective window: the
# final-head Codex observation advertised 1,050,000 while reporting 828,400 effective.  The
# app therefore sets no window, threshold or scope and records the provider's usage events.
# Task, requested scope and held-state tokens govern delivery; no character target drops
# needed content or becomes a replacement compaction cutoff.
CONTEXT_COMPACTION = {
    'claude': {'parameters': [], 'window': 'provider-owned', 'auto_compact_at': 'provider-owned'},
    'codex': {'parameters': [], 'window': 'provider-owned', 'auto_compact_at': 'provider-owned'},
}
# WHY each of those values is what it is, and what was MEASURED to settle it -- OUT of the
# session contract, because the contract rides in the KERNEL and the kernel is re-sent to
# every resumed process.  `KERNEL_MEMBERS` above carries `provider_session_policy`, so a
# reason spelled inside `session_policy()` is paid for once per resumed Claude process:
# measured 2026-10-05 with evidence/WRITING_CONSOLIDATION_2026-10-03/harness2/conformance.py
# on the S1 candidate against pre-S1 master e6bb39598, the policy was 1,218 characters
# wider and the battery's 8 resumed Claude processes delivered 9,744 characters more
# (claude.delivered_chars_on_resume 159,862 -> 169,606, [REGRESSION]).
#
# NOTHING IS DELETED.  Every string below is the one that was in the policy, verbatim, with
# its counts and its evidence paths; a session is given the VALUE it must obey and this
# module is where a reader asks why.  `session_policy()` names this dict at its own
# `reasons` key, so the declaration still says where its reasons are, and the keys are the
# policy paths the reasons belong to.
SESSION_POLICY_REASONS = {
    'instructions.frame.because':
        'the mode is the turn\'s, and one session changes mode',
    'instructions.delta.baseline':
        "the conversation's delivery receipts, in the turn row: `context_parts` for the "
        "delivery's parts and `orientation` for the brief's digests",
    'context_compaction.claude.because':
        'the CLI takes no context-window or compaction argument; its own compaction is the '
        'CLI\'s and this app cannot set it',
    'context_compaction.codex.because':
        'App Server reports the effective window in token-usage telemetry; a hard-coded '
        'catalogue maximum is not an observed runtime limit',
    'process.instructions_outside_the_contract.claude':
        'Historical neutral-cwd and setting-sources probes left user commands/agents/skills/style. '
        'They did not establish an acceptable shared instruction world. The newer safe-mode '
        'probe removed the explicit MCP gateway, so it is not an admitted closure option. '
        'Per-invocation controls preserving the gateway await independent actual inventory evidence.',
    'process.instructions_outside_the_contract.codex':
        'Installed 0.160.1 supports app-owned baseInstructions, replacing its default coding '
        'base; explicit empty developerInstructions clears the app slot. Platform Skills and '
        'multi-agent instruction extras remained in the bounded probe despite requested '
        'feature controls. They are residual, not strict parity or inventory closure proof.',
}
# The one pointer the contract carries in place of those strings: a name, not a copy.
SESSION_POLICY_REASONS_READ = 'laplace.writing.operating.SESSION_POLICY_REASONS'
# Every session-shaping argument each transport may pass: whether it is REQUIRED (and on
# which occasions), and which values the declaration permits.  Both adapters check what they
# are about to send against this before sending it.
#
# The first version of this declaration was a flat list of NAMES, checked with a set
# comparison.  That check is one-directional and value-blind, and the stage-2 judge showed
# two one-flag divergences that walked straight through it: a second `--permission-mode
# bypassPermissions` appended after the declared pair (the CLI takes the LAST occurrence, so
# the session got write authority outside the door) and a DELETED `--strict-mcp-config` (so
# the session loads whatever MCP servers the account holds instead of only the declared
# door).  `need` and `values` are therefore part of the declaration: a declared argument
# sent twice, a declared argument carrying an undeclared value, and a required argument that
# has been removed are all the same event as an undeclared argument.
#
# `need` is the occasion on which the argument must be present, and on any other occasion it
# must be absent: `always`, `project` (this session has a project), `session-start` (a
# project, and this process is not resuming), `resume`, `model`, `revise`, `effort`.
# `values` is the closed set of permitted values; `None` means the value is this turn's data
# (a brief, a session id, a JSON schema) and only its presence is checked.
TRANSPORT_ARGUMENTS = {
    'claude': {
        'surface': 'argv',
        # order matters: `arguments` IS the argv every process starts from (transport_argv).
        'arguments': {
            '-p': {'need': 'always', 'takes_value': False},
            '--output-format': {'need': 'always', 'values': ['stream-json']},
            '--include-partial-messages': {'need': 'always', 'takes_value': False},
            '--verbose': {'need': 'always', 'takes_value': False},
            # Invocation-local override; user/security/project settings remain inherited.
            '--settings': {'need': 'always', 'values': ['{"outputStyle":"default"}']},
            '--permission-mode': {'need': 'always', 'values': ['auto']},
            '--permission-prompts': {'need': 'always', 'values': ['none']},
            '--tools': {'need': 'always', 'values': ['']},
            '--effort': {'need': 'effort', 'values': None},
            # The kernel REPLACES the CLI's own base system prompt rather than being
            # appended to it, and the CLI's dynamic sections are excluded.  Decided on
            # numbers, 2026-10-05: two processes from the same empty session workspace, the
            # same kernel (19,228 chars), the same prompt, haiku low.  The two argvs that
            # were MEASURED are, verbatim, `--append-system-prompt <kernel>` at 15,102
            # first-turn context tokens and `--system-prompt <kernel>
            # --exclude-dynamic-system-prompt-sections --setting-sources ''` at 8,716, with
            # every observed property identical (door `mcp__laplace__laplace_project`
            # present and connected, the reply naming exactly that tool, no shell invented,
            # no project material) -- evidence/WRITING_JOINS_2026-10-04/S1/observed-process/
            # decision/arm-A.json and arm-C.json.
            # The pair declared HERE is that replacement MINUS `--setting-sources ''`.  Its
            # own first-turn cost was MEASURED on 2026-10-05 by one further haiku call
            # through the same instrument (the orchestrator's ruling at the round cap,
            # the packet's six-call ceiling having been spent on arms A and C): 9,079
            # first-turn context tokens, inside the derived bound [8,716, 15,102] and
            # 6,023 fewer (39.9%) than appending, with every observed property identical
            # (door present and connected, the reply naming exactly that tool, no shell
            # invented, no project material) -- evidence/WRITING_JOINS_2026-10-04/S1/
            # observed-process/decision/arm-B.json.
            # `--setting-sources ''` is NOT declared because it does not remove the $HOME
            # floor -- not because it is observationally inert.  Between the two arms the
            # floor's four members are identical (the offered slash-command, agent and skill
            # lists byte-identical, 54 / 6 / 19, and both auto memory paths present), while
            # what the runtime did report differently is `output_style`: `Explanatory`
            # without the flag, `default` with it. That historical probe did not remove
            # the floor. Current invocation --settings overrides only outputStyle to
            # default: inherited Explanatory formatting is not the app's writing style.
            # The provider init remains the observation of what actually took effect.
            '--system-prompt': {'need': 'project', 'values': None},
            '--exclude-dynamic-system-prompt-sections': {'need': 'project',
                                                         'takes_value': False},
            '--mcp-config': {'need': 'project', 'values': None},
            '--strict-mcp-config': {'need': 'project', 'takes_value': False},
            '--allowedTools': {'need': 'project',
                               'values': [CLAUDE_TOOL_PREFIX + DOOR_TOOL]},
            '--resume': {'need': 'resume', 'values': None},
            '--model': {'need': 'model', 'values': None},
            '--json-schema': {'need': 'revise', 'values': None},
        },
    },
    'codex': {
        'approvalPolicy': 'never',
        'sandbox': 'read-only',
        'thread_parameters': {
            'cwd': {'need': 'always', 'values': None},
            'approvalPolicy': {'need': 'always', 'values': ['never']},
            'sandbox': {'need': 'always', 'values': ['read-only']},
            'config': {'need': 'project', 'values': None},
            'baseInstructions': {'need': 'session-start', 'values': None},
            'developerInstructions': {'need': 'session-start', 'values': ['']},
            'dynamicTools': {'need': 'session-start', 'values': None},
            'threadId': {'need': 'resume', 'values': None},
            'model': {'need': 'model', 'values': None},
        },
        'turn_parameters': {
            'threadId': {'need': 'always', 'values': None},
            'input': {'need': 'always', 'values': None},
            'effort': {'need': 'always', 'values': None},
            'model': {'need': 'model', 'values': None},
            'outputSchema': {'need': 'revise', 'values': None},
        },
    },
}


def _occasion(need: str, occasion: dict) -> bool:
    """Whether a declared argument's occasion holds for the call being made."""
    if need == 'always':
        return True
    if need == 'session-start':
        return bool(occasion.get('project')) and not occasion.get('resume')
    return bool(occasion.get(need))


def _declared_arguments(transport: str, surface: str) -> dict:
    declaration = TRANSPORT_ARGUMENTS.get(transport) or {}
    if surface == 'argv':
        return declaration.get('arguments') or {}
    return declaration.get(surface) or {}


def transport_argv(transport: str = 'claude') -> list[str]:
    """The arguments EVERY process of this transport is given, read off the declaration.

    Derived rather than listed a second time: an `always` argument that takes a value has
    exactly one permitted value, so the declaration already is the argv.
    """
    out: list[str] = []
    for name, rule in _declared_arguments(transport, 'argv').items():
        if rule.get('need') != 'always':
            continue
        out.append(name)
        if rule.get('takes_value', True):
            out.append(rule['values'][0])
    return out


def argument_complaints(transport: str, surface: str, sent, occasion: dict) -> list[str]:
    """Every way `sent` departs from the declaration, in the declaration's own words.

    Four kinds, because four different things can be wrong and only the first was caught
    before: an argument the declaration does not name; a declared argument on an occasion
    the declaration does not permit (which includes a required one that is MISSING); a
    declared argument sent twice (the CLI takes the last, so a repeat is an override); and a
    declared argument carrying a value the declaration does not permit.
    """
    declared = _declared_arguments(transport, surface)
    if not declared:
        return [f'no declaration for {transport}/{surface}']
    occurrences: dict[str, list] = {}
    complaints: list[str] = []
    if surface == 'argv':
        index, tokens = 0, list(sent)
        while index < len(tokens):
            token = tokens[index]
            rule = declared.get(token)
            if rule is None:
                if str(token).startswith('-'):
                    complaints.append(f'{token} is not declared')
                index += 1
                continue
            value = None
            if rule.get('takes_value', True):
                value = tokens[index + 1] if index + 1 < len(tokens) else None
                index += 1
            occurrences.setdefault(token, []).append(value)
            index += 1
    else:
        for name, value in dict(sent).items():
            if name not in declared:
                complaints.append(f'{name} is not declared')
                continue
            occurrences.setdefault(name, []).append(value)
    for name, rule in declared.items():
        seen = occurrences.get(name) or []
        needed = _occasion(rule['need'], occasion)
        if needed and not seen:
            complaints.append(f'{name} is required ({rule["need"]}) and was not sent')
        if seen and not needed:
            complaints.append(f'{name} was sent on an occasion the declaration does not '
                              f'permit (it is {rule["need"]})')
        if len(seen) > 1:
            complaints.append(f'{name} was sent {len(seen)} times; the declaration permits '
                              'it once, and the later occurrence overrides the earlier')
        permitted = rule.get('values')
        if permitted is not None:
            for value in seen:
                if value not in permitted:
                    complaints.append(f'{name}={value!r} is not a value the declaration '
                                      f'permits ({permitted!r})')
    return complaints


def codex_session_config() -> dict:
    """The whole app-owned Codex config; capacity and compaction stay provider-owned."""
    return dict(CODEX_SESSION_CONFIG)


def codex_process_config_overrides(server_names=()) -> tuple[str, ...]:
    """Supported fail-closed process controls, with inherited server names derived at launch."""
    names = tuple(dict.fromkeys(server_names or ()))
    if len(names) > CODEX_MCP_SERVERS_MAX:
        raise ValueError('Too many inherited MCP servers to disable safely.')
    safe=set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-')
    if any(not isinstance(name,str) or not name or len(name)>200 or any(ch not in safe for ch in name)
           for name in names):
        raise ValueError('An inherited MCP server name cannot be represented safely.')
    features = tuple(f'features.{name}=false' for name in CODEX_PROCESS_DISABLED_FEATURES)
    servers = tuple('mcp_servers.'+name+'.enabled=false' for name in sorted(names))
    return features + servers
ROLES = {
    'discuss': 'Continue the author conversation. Carry out requested project work with the canonical tools; discussion alone is not an instruction to change artifacts.',
    'revise': 'Develop the requested exact-source manuscript revision, using project tools when needed.',
    'work': 'Develop the selected project through its canonical tools. Record working hypotheses honestly; expose actual outcomes and unresolved gaps.',
    'review': 'Independently inspect and challenge the producing work. Diagnose the consequential gaps a reader would hit (a missing step of argument, definition or explanation, at its level) and name the repair; do not saturate prose with local caveats. Bank findings and tasks; do not modify the reviewed artifacts or self-award verification.',
}
RULES = [
    'Use laplace_project for manuscript edits and structured project records so the editor and research links update together. Use store_artifact for requested project code, configuration or notes, research_producer to declare its execution contract, and experiment_run to execute it. Other host tools exist only if this session actually exposes them; never assume a shell or file tool is available. Stay within the author’s requested scope.',
    'Perform this writing session’s project work yourself. Its laplace_project tool is bound to this session and is not available to delegated workers. For a job too large for one turn, plan it with dispatch_plan, launch it with dispatch_launch, and consume what comes back with dispatch_returns: the children are writing sessions of this project with their own door and their own receipts, and the job is not done until you have read their returns and said what they establish. For connected continuation first read session_settings {view:"connection"} and use its connected_observation contract. Only an available original author admission permits dispatch_launch await_completion:true, once, with a reserved synthesis_return_path. This suspends the same tool call until state settles or the admitted connection budget ends. Never poll repeatedly, renew implicitly, replay children or start another paid parent automatically. Stop and observation expiry leave detached children supervised under their original deadline. Read the exact admitted plan/prepared input and all available worker/judge returns, including rejected outcomes. Publish parent-consumes packet-return/2 role:synthesis at the reserved path, then use inspected task_status guards to attach it. Rejected/failed/incomplete evidence cannot qualify done; retain BLOCKED synthesis and exact recovery. An interrupted original turn recovers only through an explicit Work turn in the same parent session.',
    'Use the repository operation to discover, search and read the authorised source repositories directly. Use its view action to examine original PDF pages or images. This read access does not permit cross-project edits.',
    'Use the supplied current context and exact IDs/revisions. Read a focused owner only when the needed object, revision or evidence is absent; do not reread every project surface before a routine edit. Never invent an identifier intended to refer to an existing object.',
    'Develop the logical argument with logical_plan and logical_plan_change over canonical concept objects, typed dependencies and open questions. projection_plan.json owns reader order only: chapters, sections and their concept-node IDs. Plan the reasoning before arranging its exposition.',
    'A node derives from or requires its target. Prerequisite cycles and dangling/self links are invalid; analogy is not evidence.',
    'A citation identifies a source, not a logical premise. Use support for documentary grounding; express an actual premise as a definition, assumption or result with its source_ref. Use prerequisite only for the logical claim that the inference requires.',
    'Before developing prose that presents a scientific claim as established, inspect its canonical support gaps and attach a readable source or current evidence binding. An author-introduced postulate or new proof does not need a literature citation merely to exist, but label its author origin explicitly and preserve its unreviewed, conjectural, or formal-check status instead of implying external establishment.',
    'Source outline, intended reader plan and argument/evidence are distinct. Read structure view:outline for physical headings, structure view:summary for reader sections, logical_plan for claims/support. Follow exact binding handles; inferred title/file links are not precise passage authority. Bind/rebind through the returned structure_change bind_source action; keep original selection/raw file/plan guards.',
    'Planning alone does not rewrite manuscript TeX. Use chapter and section_change to create/remove source structure (convert means a whole prose paragraph to a new heading); use source then apply_revision for exact prose or existing-heading edits, without caller expected tokens, and propose_revision when the author asks for suggestions or review before applying.',
    'For new scientific manuscript development, create or update the relevant canonical claim, attach the sources or research results it actually uses, and place it through structure_change. Each edits[] item may declare develops:[{id,content_revision}] and evidence_refs:[{id,revision}] after those owners are current and placed. evidence_refs names research results; literature uses canonical source relations and citation keys. Do not put these fields at proposal top level. Ordinary copyedits need neither declaration; a literature-grounded claim does not require an invented numerical record.',
    'A failed or partial operation is not success. MIRROR_PENDING / ineligible structure needs canonical reconciliation before manuscript production can be accepted.',
    'A current file/run proves provenance and execution only. It does not establish a scientific claim. Never award independent verified/proven/computed/imported status to your own proposal.',
    'Formal work binds the intended canonical concept through proof_targets, then proof_check with its exact concept, concept revision and source revision. proofs returns the project-specific setup paths and manifest requirements when configuration is needed. Do not invent a dummy numerical record or substitute a toy theorem for the selected claim. Ordinary authorized project dependency and library setup, including Mathlib when appropriate, needs no separate permission ceremony.',
    'UNTRACKED research means newly uncovered provenance coverage and is distinct from STALE. Inspect it, then use research_reconcile to preserve the same scientific content and complete history; reconciliation never retroactively verifies old bytes.',
    'Bind evidence only to the precise claim it supports and retain scope, assumptions, negative findings and limitations. Formal proof and informal scientific alignment remain separate.',
    'Use existing numerical producers when available. You can write and run new project code when the request needs it; retain its inputs, outputs and limitations in the project. Inspect actual output and exit status; do not infer success from an output filename.',
    'Literature workflow: literature_scope identifies support and citation gaps for the selected claims and prerequisites; task(kind="literature-acquisition") records a scoped acquisition job. Reuse project/local sources first; literature_discover also searches public metadata, and literature_lookup verifies a DOI. Import sourced metadata, use reference_fetch when readable text is absent, then reference_text to read the actual passage and obtain its reading receipt. literature_bind joins that receipt and locator to the precise claim. Place its citation in the manuscript, build, and inspect literature_scope before completing the task. Metadata or library presence alone does not qualify a claim. Use help for exact contracts.',
    'Read source contents before citing a literature claim. Zotero metadata or attachment presence is not evidence of what a paper establishes.',
    'Preserve direct author edits, scoped comments, notation, labels and exact citation identities. Propose reusable guidance for review; do not turn a local correction into global law.',
    'Saved proposal reads return exact resolution actions. Prepare and preview use read proposal@paragraph with the returned resolution view; applying uses the returned proposal decision action. Native default is compact metadata: follow text_reads, hunk.read and next_read for exact UTF-8 byte coverage and hashes, using the retained read_id handles unchanged. A contract-part is incomplete JSON until all its coverage is read; never substitute an inaccessible provider-side saved response file. Action targets carry exact file/range/source/selection guards; the owner derives their current text. Keep exact predecessor, source guard and complete owner hunk choices, or author resolved_after explicitly. A resolved current-source candidate is a real proposal with actual human or agent attribution, never a new provider turn. Source application does not renew historical scientific acceptance; inspect retained review obligations and source_effect before recovery.',
    'Use the current writing voice and presentation profiles included below. A typography choice is not a writing-voice instruction.',
    'Inspect exact candidate/build/output receipts and real preview-image media before template application. style prepares source candidates; preview never saves settings. Apply submits the owner-issued candidate_ref AND reviewed preview_ref unchanged. Source class, defaults and canonical output are separate. Report partial recording without replaying source.',
    'If an operation or payload is uncertain, inspect the deployed tool help. Do not guess a command, schema, file path or permission.',
    'Independent dispatch judges have a scoped publication permission: pass return_contract.publish_action itself as the native tool arguments, adding authored content only inside its payload. It contains operation/payload only; publication_context carries project, permission and path qualifications separately and must not be merged into the call. Use only the path/guard supplied for your own packet. session_settings returns the current authoritative return schema and publisher; help store_artifact reports this scoped permission. Ordinary review still cannot write arbitrary artifacts or reviewed source. A negative judgement belongs in the declared typed return, not only in a corrective task or conversation. Parents receive the same registered profile through parent_return_contract: use its required_reads and owner-filled scaffold/publish_action, author its conclusion, and preserve exact pins. Successful owner READ execution remains PASSED even if the evidence establishes a failed or blocked dispatch.',
    'Dispatch inspection uses the explicit laplace_project operation dispatch_status with payload:{id:the exact dispatch ID}. Its default status is small and supplies parent_return_contract.read_contract; follow that exact view:return-contract handle for the required_reads and single publish_action.payload.content scaffold. Author its conclusion fields, preserving all owner path/pins/guards, then pass publish_action itself to the native tool without adding project or publication_context. View:return-schema reads the full authoritative profile separately. Do not substitute generic read task@project, guess dispatch_id as a payload key, read a WORK ID as an artifact, or attempt provider-side saved response files through project artifacts.',
    'The supplied operation signatures are the current implementation contract. Use them directly; do not read implementation source to discover how the writer works. Read research sources only when the author task needs their substance. A structural edit to already-grounded objects normally needs current objects and revisions, not another literature pass.',
    'The author request sets scope, not the conversation label. Save requested reversible project work without asking for a mode switch. Respect requests to discuss only.',
    'The canonical operations listed in permissions are available through laplace_project and require no provider approval prompt when the author requested the work. Use store_artifact for an authorised project note or handoff; unavailable shell/file tools are not an alternative write path.',
    'When asked to develop structure, save the actual chapter/section plan and concepts with the tools. Do not substitute manuscript prose or claim an outline in chat has been saved.',
    'Carry requested changes through to the manuscript with apply_revision and placement tools. An explicit request to make a change is sufficient authorization for that reversible project work. Keep suggestions as proposals only when that is what the author asked for.',
    'Scoped progress: an action needs only its authority and the current source, target and evidence its effect consumes, never global completeness. A changed or absent derived output (a PDF or build view) does not block a source repair; it returns as review_obligations on the result. Applying is not acceptance of every claim it touches: report each pending obligation where it applies, keep useful partial results, and do not refuse or qualify unrelated work because something else is unfinished. Wrong authority, a changed current source or changed consumed evidence still refuse.',
    'Write connected movements: each section answers the question the previous one left the reader with. Put premises, definitions and evidence once, where the reader needs them, at the level of this audience; truth lives in explicit premises and evidence records, not in qualifying every sentence or narrating audit machinery to a business reader. Reviewing is diagnosis of consequential reader gaps; the author sets direction, so a finding becomes revision intent for this text, not a new universal ban.',
]

CAPABILITY_GUIDANCE = {
    'discover': 'Use help {operation} for the exact current input, outputs, preconditions and example. Do not discover by batch-calling operations with empty payloads: task and note are writes, and an empty write is never a state read.',
    'stages': 'Discover stages with writing_stage {}. Read one with {stage:"returned stage id"}; repeat with its known_revision for an unchanged handle. This prepares exact owner routes without running a model or scoring quality.',
    'source_effect': 'Source mutation returns source_effect when source bytes were observed. Read state and complete separately; COMMITTED with required work incomplete is not retry-safe. Follow returned impact.reads and exact receipts; no automatic source replay or inferred scientific reconciliation.',
    'source_read': 'Read current manuscript text with source {files:["returned source path"]}; obtain the path from the current selection or structure. source uses file/section selectors, not owner/action commands.',
    'manuscript': ['source', 'propose_revision', 'proposal_supersede', 'apply_revision', 'section_change', 'block_change'],
    'reasoning': ['logical_plan', 'logical_plan_change', 'concept', 'concept_history', 'concept_change', 'structure', 'structure_change'],
    'evidence': ['research', 'research_record', 'research_reconcile', 'experiment_run', 'visuals', 'proof_targets', 'proof_check'],
    'evidence_binding': {
        'purpose': 'Connect a current interpreted numerical result to the exact canonical claim it supports.',
        'steps': ['Read research for the result id/revision.',
                  'Read concept for the intended claim and structure for the current structure revision.',
                  'Call structure_change with operation bind_results, node, expected_concept_revision, expected_revision, and results [{id,revision}].'],
        'safeguard': 'A source_ref, matching filename, shared wording or producer completion does not identify the supported claim. Never guess or auto-attach a target.'},
    'literature': ['literature_scope', 'literature_discover', 'literature_lookup', 'literature_import', 'reference_fetch', 'reference_text', 'literature_bind', 'literature_uses'],
    'project_guidance': ['project_guidance', 'project_guidance_change'],
    'repository_images': CODE_MODE_IMAGE_GUIDANCE,
    'project_tool_responses': PROJECT_RESPONSE_GUIDANCE,
}


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str,separators=(',',':')).encode()).hexdigest()


def native_registration_signature(tool:dict,callback_protocol:str|None=None)->str:
    registration={'schema_version':NATIVE_REGISTRATION_VERSION,
        'gateway':{key:tool.get(key) for key in ('type','name','inputSchema')},
        'callback_protocol':callback_protocol or CURRENT_CALLBACK_PROTOCOL}
    return digest(registration)


def legacy_v1_registration_signature(operations)->str|None:
    """Reconstruct the known v1 gateway without borrowing today's schema."""
    if not isinstance(operations,list) or len(operations)!=len(set(operations)):
        return None
    if any(not isinstance(operation,str) or not operation for operation in operations):
        return None
    tool={'type':'function','name':'laplace_project','inputSchema':{
        'type':'object','properties':{
            'operation':{'type':'string','enum':sorted(operations)},
            'payload':{'type':'object','additionalProperties':True}},
        'required':['operation','payload'],'additionalProperties':False}}
    return native_registration_signature(tool,_LEGACY_CALLBACK_PROTOCOL_V1)


# The names a provider process must not find in the directory it RUNS IN.  Both installed
# runtimes read their own instructions out of the process working directory: the Claude CLI
# loads CLAUDE.md and the project's `.claude` (its hooks, skills, agents and memory index --
# measured 2026-10-04: a repository cwd advertised five project slash commands, the
# `atlas-worker` agent and a per-project memory path that a neutral cwd did not,
# evidence/WRITING_JOINS_2026-10-04/parity-probe/A-app-argv-repo-cwd.json against
# B-neutral-cwd.json), and the App Server reads AGENTS.md and `.codex`.  `.git` is here for
# the same reason: a checkout cwd puts a git summary of somebody else's working tree into a
# session that is only allowed what the contract gives it.
PROCESS_INSTRUCTION_NAMES = ('CLAUDE.md', '.claude', 'AGENTS.md', '.codex', '.git')
# The direct owner keeps state/session-workspaces unless portable configure deliberately
# selects LAPLACE_SESSION_WORKSPACES. Runtime state itself never needs to move.
PROCESS_WORKSPACES = 'session-workspaces'
# A process that belongs to no session: model discovery, which sends no turn.
DISCOVERY_SESSION = '_discovery'


def session_workspace_root() -> Path:
    """Existing cwd owner, with an explicit portable location independent of runtime state."""
    import os
    from laplace.engine.telemetry import state_dir
    selected = os.environ.get('LAPLACE_SESSION_WORKSPACES')
    return (Path(selected).expanduser().resolve() if selected
            else (state_dir() / PROCESS_WORKSPACES).resolve())


def session_workspace_name(session: str | None) -> str:
    return ''.join(character if (character.isalnum() or character in '-_') else '-'
                   for character in str(session or '').strip()) or DISCOVERY_SESSION


def _undeclared_instructions(directory: Path) -> list[dict]:
    """The directory a process would run in, AND every ancestor up to $HOME, that carries
    one of `PROCESS_INSTRUCTION_NAMES` -- each with the names found there.

    Both installed runtimes walk UP from the directory they run in, so an EMPTY directory
    inside a project is still that project's session: measured 2026-10-05 on the installed
    CLI, a workspace at `<checkout>/.laplace-state-probe/session-workspaces/P1` offered this
    repository's own `serve-walk` command and seven agents -- what the checkout itself
    offered, not what a neutral directory offered
    (evidence/WRITING_JOINS_2026-10-04/S1/session-workspace/cli-cwd-probe/summary.json).
    $HOME and above are the USER-level floor no choice of working directory can move
    (`~/.claude` is loaded for every cwd), so the walk STOPS there, and what that floor
    leaves in a session is NAMED with its measured counts in `session_policy` rather than
    refused here.  ONE stop rule: the conformance harness measures with the same one
    (`harness2/_conformance_worker.process_observation`), so the app and the instrument
    answer "what can this process still read" the same way.
    """
    home = Path.home()
    found: list[dict] = []
    for index, candidate in enumerate((directory, *directory.parents)):
        if index and (candidate == home or candidate in home.parents
                      or candidate == Path(candidate.root)):
            break
        present = sorted(name for name in PROCESS_INSTRUCTION_NAMES
                         if (candidate / name).exists())
        if present:
            found.append({'dir': str(candidate), 'names_present': present})
    return found


def session_workspace(session: str | None = None) -> Path:
    """The directory a provider process RUNS IN: empty, and never the checkout.

    ONE function for both transports, because "what is this process's working directory"
    is one question and the two adapters were two answers to it: the Claude CLI was spawned
    in the checkout (`subprocess.Popen(..., cwd=self.cwd)`) and the App Server was started
    and given its thread `cwd` there too, so each session was handed this repository's
    CLAUDE.md, `.claude`, AGENTS.md and git state -- instructions no contract of ours
    declares and no instruction measurement of this campaign can see.  The checkout is
    still the DOOR's root (`writing_tools --root`, `writing_tools.execute`): the process
    runs nowhere, the door reads the project.

    The conventional way to shut this off is a transport flag -- `--setting-sources ""` or
    `--bare`.  Measured 2026-10-04 (evidence/WRITING_JOINS_2026-10-04/parity-probe): the
    first leaves CLAUDE.md and the memory index in place, and the second kills subscription
    authentication.  An empty working directory is the one control both runtimes obey,
    because it is the input they derive those instructions FROM.
    """
    # A session id names a directory, so it is reduced to one path segment: every character
    # outside [A-Za-z0-9-_] becomes '-', which is also what forbids '..' and any separator
    # from escaping the workspaces root.  Provider session ids and the app's own are hex,
    # uuids and dashes, so this renames nothing that occurs in practice.
    from filelock import FileLock
    base = session_workspace_root()
    base.mkdir(parents=True, exist_ok=True)
    workspace = base / session_workspace_name(session)
    with FileLock(str(base / '.cleanup.lock'), timeout=10):
        if workspace.is_symlink():
            raise ValueError('Session workspace must be an owned directory, not a symlink: %s' % workspace)
        workspace.mkdir(parents=True, exist_ok=True)
    # The guarantee, verified rather than assumed, and FAIL CLOSED: this app would rather
    # refuse a turn than hand a session instructions it never declared.  Contract amendment
    # 4 (orchestrator, 2026-10-05): the guarantee wins over the location, so what is checked
    # is not this directory alone but the whole set a runtime reads from -- the directory and
    # every ancestor up to $HOME.  A provider that drops one of the names into its own cwd,
    # and an explicitly selected cwd inside a checkout are both worth refusing; the refusal
    # names the directory and the file so the launch that caused it is obvious.
    outside = _undeclared_instructions(workspace)
    if outside:
        raise ValueError(
            'Session workspace %s carries instructions outside the contract: %s'
            % (workspace, '; '.join('%s in %s' % (', '.join(entry['names_present']),
                                                  entry['dir']) for entry in outside)))
    return workspace


def session_policy(tool: dict | None = None) -> dict:
    """THE session contract: what a provider session is given, and when.

    One declaration, read by both transports in `writing_provider` for every decision each
    of them used to spell by hand.  A transport may choose only the CHANNEL that carries a
    value, never the value: the channels it may choose are named here too, per transport,
    where the two providers have no common vocabulary (there is no sandbox flag on the
    Claude CLI and no parameter that withdraws an App Server thread's own tools).
    """
    from laplace.native import tools as writing_tools
    from laplace.writing.provider import EDIT_SCHEMA
    tool = tool or writing_tools.specification()
    return {
        'schema_version': SESSION_POLICY_VERSION,
        # Where this contract's own reasons live, said once.  The VALUES ride in the kernel
        # because a session must obey them; the reasons do not, because no session acts on
        # them and every resumed process would pay for them again.
        'reasons': SESSION_POLICY_REASONS_READ,
        'instructions': {
            'kernel': {'members': KERNEL_MEMBERS, 'header': KERNEL_HEADER,
                       'deliver': 'every-process-where-the-transport-forces-it',
                       'invariant_within_a_session': True},
            'frame': {'members': FRAME_MEMBERS, 'header': FRAME_HEADER,
                      'deliver': 'every-turn', 'channel': 'user-turn'},
            'body': {'members': BODY_MEMBERS, 'header': BODY_HEADER,
                     'deliver': 'once-at-session-start',
                     'channel': {'claude': 'first-user-turn-retained-by-resume',
                                 'codex': 'first-user-turn-retained-by-resume'},
                     # ONE fact per field: this one is the bytes (0 on a resumed process,
                     # on both transports, which `conformance.py`'s
                     # `instruction_body_chars_on_a_resume` asserts in those words).  That
                     # the session is TOLD what the resume withheld is the delta's fact and
                     # lives once, below, in `delta.withheld_on_a_resume_without_a_delta`.
                     'on_resume': 'never-redelivered',
                     'reads': BODY_READS,
                     'redeliver': 'on-digest-change-as-a-delta',
                     'delta_producer': 'laplace.writing.operating.turn_delta',
                     'delta_channel': 'user-turn'},
            # ONE delta, one channel, one producer, both transports.  What a resumed
            # session already holds and what moved since its last turn is one question,
            # and two blocks under two grammars were two answers to it.  The producer is
            # the only site that writes the block; `orientation_delta` below computes the
            # brief half of its content and no longer delivers anything itself.
            'delta': {'header': DELTA_HEADER, 'channel': 'user-turn',
                      'producer': 'laplace.writing.operating.turn_delta',
                      'carries': ['already_delivered', 'changed'],
                      'identical_on_both_transports': True,
                      'every_withheld_part_names_its_read': True,
                      'brief_half': 'laplace.writing.operating.orientation_delta',
                      'delivery_half': 'laplace.writing.turn_context.without_already_delivered',
                      'withheld_on_a_resume_without_a_delta': 'none'},
            'block_join': BLOCK_JOIN,
            'carries_absolute_host_paths': False,
        },
        'output_style': {'claude': {'requested': 'default', 'scope': 'invocation-only',
                                  'control': '--settings', 'observed_in': 'provider init'}},
        'tool': {'name': DOOR_TOOL, 'visible_name': dict(TOOL_VISIBLE_NAME),
                 'declared_once': True, 'retained_across_resume': True,
                 'input_schema': {'digest': digest(tool.get('inputSchema'))},
                 'declaration': {'digest': digest(tool)},
                 'native_registration_signature': native_registration_signature(tool),
                 # One semantic project gateway, with the unavoidable provider surface named
                 # rather than fabricated as a one-tool inventory. Claude withdraws its native
                 # tools; App Server retains provider-native read tools beside dynamicTools.
                 'native_surface': {
                     'claude': {'state': 'withdrawn', 'control': '--tools= plus --strict-mcp-config',
                                'write_authority': 'none', 'network': 'none'},
                     'codex': {'state': 'provider-native-capability-closure-unproven',
                               'inventory': 'inherited MCP names resolved and disabled at launch',
                               'write_authority': 'none after effective process preflight',
                               'network': 'none after effective process preflight'}}},
        'write_authority': {'outside_the_door': 'none',
                            'sandbox': {'claude': 'no-native-tools', 'codex': 'read-only'},
                            'effective_closure': {'claude': 'requested-native-withdrawal;inventory-observed-per-process',
                                                  'codex': 'inherited-MCP-preflight-only;native-residual-unproven'},
                            'declared_exception': None,
                            'rationale_record': 'evidence/WRITING_CONSOLIDATION_2026-10-03/'
                                                'harness2/baseline/write_authority.json'},
        'network': {'outside_the_door': 'none',
                    'controls': {'claude': '--tools=',
                                 'codex': {'web_search': 'disabled', 'sandbox': 'read-only',
                                           'process_features': list(CODEX_PROCESS_DISABLED_FEATURES),
                                           'inherited_mcp': 'each resolved name enabled=false'}},
                    'effective_closure': {'claude': 'requested-native-withdrawal;inventory-observed-per-process',
                                          'codex': 'inherited-MCP-preflight-only;native-residual-unproven'},
                    'door_operations_that_reach_the_network': NETWORK_DOOR_OPERATIONS},
        # WHERE the process runs, and therefore what it is given that no block of
        # instructions above carries.  One declaration for both transports, beside the
        # instruction channels, because a working directory is an instruction channel: it
        # is where each installed runtime reads its own project documents, hooks and git
        # state from.  No path here: the workspace is named by its PROPERTY (empty), and the
        # path is `session_workspace`'s to resolve, so these bytes carry no host path
        # (`instructions.carries_absolute_host_paths: False`).
        #
        # Each transport's entry is the ANSWER, as a declared value: what the empty
        # workspace removed, and what the $HOME floor still leaves.  The counts that
        # settled it, the arguments tried against the floor and the probe files that
        # recorded them are in `SESSION_POLICY_REASONS` under these same two paths, named
        # once by `reasons` below -- they are a reader's question, and they cost every
        # resumed process 1,218 characters while they rode here (see that dict's comment).
        'process': {'workspace': 'empty-session-workspace',
                    'workspace_owner': 'laplace.writing.operating.session_workspace_root',
                    'instructions_outside_the_contract': {
                        'claude': 'project-material-excluded;cli-base-prompt-replaced;user-customizations-closure-unproven',
                        'codex': 'project-docs-off;app-baseInstructions-sent;platform-extra-instructions-uncontrolled'}},
        'interactive_approval': 'none',
        'resume': {'conversation': 'provider-owned',
                   'instructions': 'installed-runtime-retains-start-kernel; changed-or-unproven-kernel-rebinds',
                   'tool_registration': 'retained-by-the-thread-not-resent',
                   'exact_content_after_provider_compaction': 'unverified-by-this-app'},
        'turn_output': {'required': TURN_OUTPUT_REQUIRED, 'optional': TURN_OUTPUT_OPTIONAL,
                        'status_values': TURN_STATUS_VALUES,
                        'provider_stage_values': ['pre-inference','inference'],
                        'edit_schema': {'digest': digest(EDIT_SCHEMA)}},
        'usage': {'projection': USAGE_PROJECTION,
                  'scope': 'usage_basis labels compatibility projection; usage_facts selects explicit counter scopes',
                  'facts_schema': USAGE_FACTS_VERSION,
                  'facts_contract_read': 'laplace.writing.operating.USAGE_FACTS_CONTRACT',
                  'context_tokens_used': 'latest request input proxy, never conversation aggregate or exact occupancy',
                  'total_when_unreported': 'sum only when all disjoint components are known',
                  'reasoning_output_folded_into_output': {'claude': True, 'codex': True}},
        'delivery_receipt': {'schema_version':DELIVERY_RECEIPT_VERSION,
                             'contract_read':'laplace.writing.operating.DELIVERY_RECEIPT_CONTRACT'},
        'failure_receipt': {'body_producer': 'laplace.native.tools.failure_response',
                            'row_producer': 'laplace.native.tools.bank_failure',
                            'row': 'writing-tool-failure',
                            'row_file': 'contract/talk.jsonl',
                            'row_fields': FAILURE_ROW_FIELDS,
                            'operation_chars_max': FAILURE_OPERATION_CHARS_MAX,
                            'payload_bounded_by': FAILURE_PAYLOAD_BOUND,
                            'banked_exactly_once_per_failure': True},
        'cancellation': {'claude': 'SIGTERM-to-the-process-group', 'codex': 'turn/interrupt'},
        'context_compaction': CONTEXT_COMPACTION,
        'events': 'own-thread-and-turn',
        'transport_arguments': TRANSPORT_ARGUMENTS,
        'codex_process': {'disabled_features': list(CODEX_PROCESS_DISABLED_FEATURES),
                          'required_feature': 'code_mode_host for the client-executed dynamic project gateway',
                          'mcp_resolution': 'effective config metadata before initialized, names only',
                          'mcp_control': 'mcp_servers.<resolved-name>.enabled=false',
                          'verification': 'effective config disabled, zero tools, and no active runtime before thread start',
                          'limits': {'servers': CODEX_MCP_SERVERS_MAX,
                                     'pages': CODEX_MCP_STATUS_PAGES_MAX}},
        'codex_config': CODEX_SESSION_CONFIG,
    }


def visible_tool_name(transport: str | None) -> str:
    """The door's name as THIS session will see it; the door's own name when unknown."""
    return TOOL_VISIBLE_NAME.get(str(transport or ''), DOOR_TOOL)


def role_permissions():
    """Existing declared role ceiling, shared without constructing prompt/schema bodies."""
    from laplace.writing import reads
    return {mode:sorted(reads.READS | ({'note','note_status','task','work_review'} | {op+':'+a for op, acts in reads.ACTION_READS.items() for a in sorted(acts)} if mode=='review' else reads.WRITES)) for mode in ROLES}


def tool_contract():
    """The brief's view of the deployed contract: digests and routes, not a second copy.

    `operation_payload_contracts` used to carry four owners' whole schemas, which the
    brief then shipped on every turn (`build` below) while `help {operation}` returned
    the same bytes again under `requested_payload_contract`
    (`src/laplace/writing_tools.py:271`, now gone).  The brief now carries the
    declarations' digest and the one route that reads a declaration, so a turn is told
    where the contract is rather than given it twice.
    """
    from laplace.native import tools as writing_tools, declarations as writing_declarations
    from laplace.writing import reads
    from laplace.writing.provider import EDIT_SCHEMA
    exact_actions={operation:writing_declarations.contract_semantics(
        writing_declarations.help_payload(operation,permitted=True,with_tokens=False,full=True))
        for operation in sorted(reads.READS|reads.WRITES)}
    payload_contracts={'exact_actions_digest':digest(exact_actions),
                       'read_one':{'operation':'help','payload':{'operation':'<operation>'}},
                       'read_one_variant':{'operation':'help',
                                           'payload':{'operation':'<operation>',
                                                      'variant':'<variant>'}},
                       'http_door':{'operation':'help','payload':{'door':'http'}},
                       'declared_in':'laplace.native.declared'}
    tool=writing_tools.specification()
    native_registration={'schema_version':NATIVE_REGISTRATION_VERSION,
        'gateway':{key:tool.get(key) for key in ('type','name','inputSchema')},
        'callback_protocol':CURRENT_CALLBACK_PROTOCOL}
    value={'schema_version':VERSION,'tool':tool,'edit_response_schema':EDIT_SCHEMA,
           'provider_session_policy':session_policy(tool),
           'native_registration_signature':native_registration_signature(tool),
           'native_registration':native_registration,
           'operation_payload_contracts':payload_contracts,
           'exact_actions_digest':digest(exact_actions),
           'exact_action_digests':{operation:digest(contract) for operation,contract in exact_actions.items()},
           'action_catalogue':writing_declarations.catalogue(reads.READS | reads.WRITES),
           'read_homes':writing_declarations.native_read_homes(),
           'generic_actions':[home for home in writing_declarations.native_homes() if home['verb']!='read'],
           'role_permissions':role_permissions()}
    value['action_catalogue_digest']=digest(value['action_catalogue'])
    from laplace.writing.dispatch_returns import REVIEW_PERMISSION
    value['conditional_role_permissions']={'review':[REVIEW_PERMISSION]}
    value['role_permissions_digest']=digest({'unconditional':value['role_permissions'],'conditional':value['conditional_role_permissions']})
    return {**value,'digest':digest(value)}


def build(project, mode, root, workspace_context=None, *, session_id=None, dispatch_id=None, turn_id=None):
    if mode not in ROLES:
        raise ValueError('Unknown writing role')
    from laplace.manuscript import manuscript_source, document_style, project_protocol
    from laplace.projects import writing_sources
    root=Path(root).resolve()
    contract=tool_contract()
    source=manuscript_source.resolve(project,repo_root=root)
    try:
        presentation=document_style.defaults_status(project,root)
    except ValueError as error:
        presentation={'status':'UNAVAILABLE','reason':str(error),'effective_origin':'unavailable'}
    try:
        from laplace.manuscript import writing_style
        voice=writing_style.context(project,root)
    except ImportError:
        # Explicitly unavailable during bootstrap; never substitute an invented style.
        voice={'status':'UNAVAILABLE','reason':'Writing-style context producer is not installed.'}
    from laplace.pipeline import narrative
    architecture = narrative.architecture_status(root)
    protocol = project_protocol.load(project, root)
    live_scope = {'selected_source': {key: source.get(key) for key in
                                     ['root','edition','revision','read_only','status']},
                  'workspace': workspace_context or {}}
    from laplace.native import declarations as writing_declarations
    guidance={**CAPABILITY_GUIDANCE,'read_homes':[
        {key:home[key] for key in ('verb','concept','native_request','owner_read','basis')}
        for home in writing_declarations.native_read_homes(project)],
        'generic_actions':[{key:home[key] for key in ('verb','concept','native_request','owner_read','basis','permission') if key in home}
            for home in writing_declarations.native_homes(project) if home['verb']!='read']}
    scoped=[]
    if mode=='review' and session_id and dispatch_id:
        from laplace.writing.dispatch_returns import child_permission, publication_projection
        permitted=child_permission(root,project,session_id,dispatch_id,turn_id=turn_id)
        if permitted:scoped=[permitted]
    brief={'schema_version':VERSION,'tool_contract_digest':contract['digest'],
           'native_registration_signature':contract['native_registration_signature'],
           'exact_action_digests':contract['exact_action_digests'],
           'action_catalogue_digest':contract['action_catalogue_digest'],
           'role_permissions_digest':contract['role_permissions_digest'],
           'shared_rules_revision':digest(RULES),
           'capability_guidance_revision':digest(guidance),'project':project,
           'provider_session_policy':contract['provider_session_policy'],
           'mode':mode,'role':ROLES[mode],'workspace':workspace_context or {},
           'permissions':sorted(set(contract['role_permissions'][mode])|{row['operation'] for row in scoped}),
           'scoped_permissions':[publication_projection(row) for row in scoped] if scoped else contract['conditional_role_permissions'].get(mode,[]),'rules':RULES,
           'orientation_layers': {
               'shared': 'rules and capability_guidance',
               'project': 'project_protocol instruction bodies and guide identities',
               'live': 'live_scope, canonical records and exact tool reads',
           },
           'capability_guidance': guidance,
           'selected_source':live_scope['selected_source'], 'live_scope': live_scope,
           'writing_style':voice,'architecture_prior':architecture,'presentation':presentation,
           'project_protocol':protocol,
           'source_repositories':writing_sources.inventory(root),
           # The operation contract is the tool's own declaration plus the digest of the
           # 73 operation declarations and the route to read one.  It is not the 73
           # contracts: those were 220,797 characters and the brief shipped the four
           # owner schemas of them on every turn.
           'operation_contract':{**contract['tool'],
                                 'exact_actions_digest':contract['exact_actions_digest'],
                                 'read_one':{'operation':'help',
                                             'payload':{'operation':'<operation>'}}},
           'operation_payload_contracts':contract['operation_payload_contracts'],
           'response_contract':contract['edit_response_schema'] if mode == 'revise' else {'answer':'plain text; use propose_revision only for requested manuscript changes'}}
    brief['digest']=digest(brief)
    return brief


def orientation_delta(previous, current):
    """The BRIEF HALF of the one turn delta: only the guidance whose digest moved.

    Native provider instructions are immutable after a thread starts and a Claude process
    is given the kernel alone, so the project body a resumed session already holds is
    re-delivered as this bounded change and never whole.  This function COMPUTES that
    change; it no longer delivers it.  `turn_delta` below is the one producer of the one
    block, and the contract names it (`session_policy()['instructions']['delta']`).
    """
    previous = previous if isinstance(previous, dict) else {}
    changes = {}
    if previous.get("shared_rules_revision") != current.get("shared_rules_revision"):
        changes["shared_rules_revision"] = current.get("shared_rules_revision")
        changes["rules"] = current.get("rules")
    if previous.get("capability_guidance_revision") != current.get("capability_guidance_revision"):
        changes["capability_guidance_revision"] = current.get("capability_guidance_revision")
        changes["capability_guidance"] = current.get("capability_guidance")
    if previous.get("tool_contract_digest") != current.get("tool_contract_digest"):
        changes["tool_contract_digest"] = current.get("tool_contract_digest")
        prior_actions=previous.get('exact_action_digests')
        current_actions=current.get('exact_action_digests') or {}
        changed_actions=(sorted(operation for operation,digest_value in current_actions.items()
                                if prior_actions.get(operation)!=digest_value)
                         if current_actions and isinstance(prior_actions,dict) else [])
        changes["contract_delta"]={
            "changed_actions":changed_actions[:40],
            "changed_actions_omitted":max(0,len(changed_actions)-40),
            "prior_action_detail_available":isinstance(prior_actions,dict),
            "catalogue_changed":(previous.get('action_catalogue_digest')!=current.get('action_catalogue_digest')
                                 if previous.get('action_catalogue_digest') else None),
            "permissions_changed":(previous.get('role_permissions_digest')!=current.get('role_permissions_digest')
                                   if previous.get('role_permissions_digest') else None),
            "read_exact":{"operation":"help","payload":{"operation":"<changed action>"}},
            "note":"Exact help, preconditions or examples changed. Read help only for an action needed by this turn."}
    source = current.get("selected_source") or {}
    old_source = previous.get("selected_source") or {}
    if {key: source.get(key) for key in ("root", "edition", "revision")} != {
            key: old_source.get(key) for key in ("root", "edition", "revision")}:
        changes["selected_source"] = source
    voice = current.get("writing_style") or {}
    old_voice = previous.get("writing_style") or {}
    voice_keys = ("revision", "selected_profile", "profile_revision", "guidance_sha256")
    if {key: voice.get(key) for key in voice_keys} != {key: old_voice.get(key) for key in voice_keys}:
        changes["writing_style"] = voice
    architecture = current.get('architecture_prior') or {}
    old_architecture = previous.get('architecture_prior') or {}
    if architecture.get('revision') != old_architecture.get('revision'):
        changes['architecture_prior'] = architecture
    protocol = current.get("project_protocol") or {}
    old_protocol = previous.get("project_protocol") or {}
    if protocol.get("revision") != old_protocol.get("revision"):
        changes["project_protocol"] = protocol
    if previous.get("workspace") != current.get("workspace"):
        changes["workspace"] = current.get("workspace") or {}
    return {"changed": bool(changes), "guidance": changes}


def body_already_delivered(brief) -> list[dict]:
    """The project body as delta rows: one row per member, each naming its own read.

    The body is delivered once per session and withheld on every resumed process.  Before
    this, that withholding was the only one in the system that told the session nothing:
    the delivery's parts each named the read that returns them and the body named nothing.
    These rows give it the same grammar, from the contract's own `BODY_READS`.
    """
    members = instruction_members(brief if isinstance(brief, dict) else {})
    rows = []
    for key in BODY_MEMBERS:
        if key not in members:
            continue
        rows.append({'part': 'operating_brief.' + key,
                     'chars': len(json.dumps(members[key], ensure_ascii=False,
                                             separators=(',', ':'))),
                     'read': {'operation': BODY_READS[key]['operation'],
                              'payload': dict(BODY_READS[key]['payload'])}})
    return rows


def body_parts(brief) -> list[dict]:
    """Project guidance uses the conversation's existing per-part token baseline too."""
    members = instruction_members(brief)
    parts = []
    for key in BODY_MEMBERS:
        if key not in members:
            continue
        text = _block('LAPLACE OPERATING BRIEF — CHANGED PROJECT STATE', {key: members[key]})
        parts.append({'key': 'operating_brief.' + key, 'token': digest(members[key]), 'value': members[key],
                      'text': text, 'chars': len(text),
                      'read': {'operation': BODY_READS[key]['operation'],
                               'payload': dict(BODY_READS[key]['payload'])}})
    return parts


def turn_delta(previous, current, already_delivered=(), *, changed_body=None) -> dict:
    """THE one delta a continuing session is given, in the one channel the contract names.

    `previous`/`current` are the orientation snapshots this conversation's last turn banked
    and this turn built; `already_delivered` is every part this conversation already holds,
    each with the declared read that returns it (the delivery's withheld parts and, on a
    resumed process, the project body's members).  One block, one grammar, identical on
    both transports, because both carry the user turn verbatim.
    """
    # Body members are delivered by the same part comparison as manuscript context.
    # Do not also repeat them through the older orientation snapshot comparison.
    guidance = {key: value for key, value in
                (orientation_delta(previous, current).get('guidance') or {}).items()
                if key not in BODY_MEMBERS}
    guidance.update(changed_body or {})
    held = [{'part': str(row.get('part') or ''), 'chars': int(row.get('chars') or 0),
             'read': row.get('read')}
            for row in (already_delivered or ()) if isinstance(row, dict)]
    value: dict = {}
    if held:
        value['already_delivered'] = held
    if guidance:
        value['changed'] = guidance
    block = ''
    if value:
        block = (DELTA_HEADER + '\n' + DELTA_PROSE + '\n'
                 + json.dumps(value, ensure_ascii=False))
    return {'block': block, 'changed': guidance, 'already_delivered': held,
            'chars': len(block)}


def process_instructions(brief, transport, *, resumed: bool) -> dict:
    """One shared semantic frame, with only the tool alias and wire channel varied.

    The kernel replaces each provider's base slot. Project body and current frame ride
    in the user channel on both. A resume withholds the body and names its current read
    through the existing turn delta; provider-owned retention remains unobservable.
    """
    if brief.get('reader_profile'):
        from laplace.writing.sealed_reader import KERNEL
        if transport!='claude' or resumed:raise ValueError('Sealed text reader requires a fresh Claude process.')
        return {'session_slot':KERNEL,'turn_prefix':'','body_delivered':False,'body_withheld_named_in_the_delta':[]}
    name = str(transport or '')
    if name not in ('claude', 'codex'):
        raise ValueError('Unknown transport for the session instructions: ' + name)
    turn_blocks = [] if resumed else [body(brief)]
    turn_blocks.append(frame(brief))
    session_slot = '' if resumed and name == 'codex' else kernel(brief, name)
    return {'session_slot': session_slot,
            'turn_prefix': BLOCK_JOIN.join(turn_blocks),
            'body_delivered': not resumed,
            'body_withheld_named_in_the_delta': body_already_delivered(brief) if resumed else []}


def delivery_receipt(brief, transport, task, *, resumed=False):
    """Prepared fingerprints, promoted by the adapter only after actual writes.

    Canonical hashes describe app meaning; wire hashes preserve the alias-specific bytes.
    Neither a successful write nor requested controls prove provider-native inventory or
    retention after compaction. The exact context/consumed references stay on the turn.
    """
    def pin(text):
        raw=str(text).encode('utf-8')
        return {'sha256':'sha256:'+hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    blocks=process_instructions(brief,transport,resumed=resumed)
    texts={'kernel':kernel(brief,transport),'body':body(brief),'frame':frame(brief),'task':task}
    canonical={key:pin(text.replace(TOOL_VISIBLE_NAME['claude'],DOOR_TOOL) if key=='kernel' else text) for key,text in texts.items()}
    parts={key:{'state':'WITHHELD' if resumed and key=='body' or resumed and key=='kernel' and transport=='codex' else 'PREPARED',
                 'canonical':canonical[key],'wire':pin(text)} for key,text in texts.items()}
    return {'schema_version':DELIVERY_RECEIPT_VERSION,'provider':transport,
        'app_semantic_digest':digest(canonical),'parts':parts,
        'request_fingerprint_basis':'canonical JSON of argument/parameter values; excludes transport framing',
        'channels':{'kernel':'baseInstructions' if transport=='codex' else '--system-prompt',
                    'body':'user-turn','frame':'user-turn','task':'user-turn'},
        'withheld_reads':blocks['body_withheld_named_in_the_delta'],
        'provider_retention':{'state':'UNOBSERVABLE'},
        'platform_extra_instructions':{'state':'UNOBSERVABLE','strict_parity':'unproven'},
        'native_inventory':{'state':'UNOBSERVABLE','requested_controls_are_proof':False}}


def instruction_members(brief):
    """Every member the instructions carry, before the kernel/body partition.

    Full contracts stay reachable through help and the audit receipt; tool declarations
    already carry operation descriptions.  The current target belongs to the turn, not to
    immutable provider instructions, which also keeps a Claude process's system slot
    stable across resumes.
    """
    compact = {key: value for key, value in brief.items() if key not in INSTRUCTIONS_OMIT}
    protocol = brief.get('project_protocol') or {}
    compact['project_protocol'] = {
        'project': protocol.get('project'), 'revision': protocol.get('revision'),
        'documents': [row for row in protocol.get('documents') or []
                      if row.get('role', 'instructions') == 'instructions'],
        'read_more': 'project_guidance discovers current handoff/background documents on demand',
    }
    return compact


def _block(header, value):
    return header + '\n' + json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def kernel(brief, transport=None):
    """The session-invariant instruction block, named for the transport that carries it.

    A member the partition does not name rides here, visibly, rather than being dropped:
    the kernel is what every process of a session may be re-given, so an unclassified
    member is delivered rather than lost, and the harness reports it as unclassified.
    """
    if brief.get('reader_profile'):
        from laplace.writing.sealed_reader import KERNEL
        return KERNEL
    members = instruction_members(brief)
    visible = visible_tool_name(transport)
    value = {key: members[key] for key in KERNEL_MEMBERS if key in members}
    value.update({key: members[key] for key in members
                  if key not in KERNEL_MEMBERS and key not in FRAME_MEMBERS
                  and key not in BODY_MEMBERS})
    value['tool_visible_name'] = visible
    if visible != DOOR_TOOL:
        # RULES[0] and RULES[1] name the door.  On a transport that namespaces it, the
        # unprefixed name is a tool this session cannot see.
        value['rules'] = [rule.replace(DOOR_TOOL, visible) if isinstance(rule, str) else rule
                          for rule in value.get('rules') or []]
    return _block(KERNEL_HEADER, value)


def frame(brief):
    """This turn's mode, role, permissions and response contract: every turn, both transports."""
    if brief.get('reader_profile'):return ''
    members = instruction_members(brief)
    return _block(FRAME_HEADER, {key: members[key] for key in FRAME_MEMBERS if key in members})


def body(brief):
    """This project's current state: delivered once for a session, never on a resume."""
    if brief.get('reader_profile'):return ''
    members = instruction_members(brief)
    return _block(BODY_HEADER, {key: members[key] for key in BODY_MEMBERS if key in members})


def prompt(brief, transport=None):
    """The session's instructions: what a session is given when it STARTS, and only then.

    The turn frame is not here; it belongs to the turn and each adapter carries it with the
    turn text (`frame` above).
    """
    return kernel(brief, transport) + BLOCK_JOIN + body(brief)


def validate_provider_metadata(row):
    """Additive owner gate; historical replies lacking these fields stay untouched."""
    from laplace.core.identity import require_schema_version
    facts=row.get('usage_facts')
    if isinstance(facts,dict) and facts.get('schema_version')==USAGE_FACTS_VERSION:
        require_schema_version(facts,(USAGE_FACTS_VERSION,),owner='Provider usage facts')
        observations=facts.get('observations',[])
        if not isinstance(observations,list) or any(not isinstance(item,dict) for item in observations):raise ValueError('Provider usage observations must be a list of objects')
        ids={item.get('observation_id') for item in observations}
        if len(ids)!=len(observations) or None in ids:raise ValueError('Provider usage observation identities must be unique')
        by_id={item['observation_id']:item for item in observations}
        for item in observations:
            counts=item.get('counts')
            if not isinstance(counts,dict) or set(counts)!=set(USAGE_FACTS_CONTRACT['counts']) or any(value is not None and (not isinstance(value,int) or isinstance(value,bool) or value<0) for value in counts.values()):raise ValueError('Provider usage counts must be nonnegative integers or explicit unknowns')
            if item.get('counter_scope') not in USAGE_FACTS_CONTRACT['counter_scopes'] or item.get('phase') not in USAGE_FACTS_CONTRACT['phases'] or item.get('counter_domain') not in USAGE_FACTS_CONTRACT['counter_domains']:
                raise ValueError('Undeclared provider usage vocabulary')
        selected=facts.get('selected') or {}
        if not isinstance(selected,dict):raise ValueError('Provider usage selection must be an object')
        for key in USAGE_FACTS_CONTRACT['selection_keys']:
            values=selected.get(key) if key=='unselected_variants' else [selected.get(key)]
            if not isinstance(values,list):raise ValueError('Provider usage variant references must be a list')
            for value in values or []:
                if value:
                    if not isinstance(value,dict):raise ValueError('Provider usage selection must be an observation reference')
                    if value.get('observation_id') not in ids:
                        raise ValueError('Provider usage selection does not name a saved observation')
                    original=by_id[value['observation_id']]
                    if original.get('reset_epoch')!=facts.get('reset_epoch'):
                        raise ValueError('Provider usage selection belongs to an earlier reset epoch')
                    for field in ('counts','counter_domain','raw_observation_ref','completeness','reported_cost_estimate'):
                        if value.get(field)!=original.get(field):raise ValueError('Provider usage selection differs from its saved observation')
                    same_scope=value.get('counter_scope')==original.get('counter_scope')
                    same_basis=value.get('basis')==original.get('basis')
                    if key=='context_snapshot':
                        if original.get('counter_scope')!='last_request' or value.get('counter_scope')!='context_snapshot' or not same_basis or value.get('metric')!=USAGE_CONTEXT_PROXY_METRIC or value.get('value')!=original.get('context_input_proxy') or value.get('exact_post_compaction_occupancy')!='UNOBSERVABLE':
                            raise ValueError('Context proxy must name its exact request observation')
                    elif key=='logical_turn' and original.get('counter_scope')=='binding_cumulative':
                        baseline=facts.get('baseline') or {}
                        zero=baseline.get('value')
                        established_zero=isinstance(zero,dict) and set(zero)==set(USAGE_FACTS_CONTRACT['counts']) and all(type(count) is int and count==0 for count in zero.values())
                        if facts.get('provider')!='codex' or value.get('counter_scope')!='logical_turn' or value.get('basis')!=USAGE_FRESH_BINDING_BASIS or value.get('baseline')!=baseline or baseline.get('kind')!='zero_fresh_binding' or not facts.get('native_binding_id') or baseline.get('native_binding_id')!=facts.get('native_binding_id') or original.get('native_binding_id')!=facts.get('native_binding_id') or baseline.get('reset_epoch')!=facts.get('reset_epoch') or not established_zero or original.get('completeness')!='complete_for_reported_scope':
                            raise ValueError('Logical total requires an established fresh binding baseline')
                    elif not same_scope or not same_basis or original.get('counter_scope')!=('unknown' if key=='unselected_variants' else key):
                        raise ValueError('Provider usage selection cannot promote or relabel its observation scope')
    elif facts is not None:
        from laplace.core.bodies import is_reference
        if not is_reference(facts):require_schema_version(facts,(USAGE_FACTS_VERSION,),owner='Provider usage facts')
    receipt=row.get('delivery_receipt')
    if receipt is not None:
        from laplace.core.bodies import is_reference
        if not is_reference(receipt):require_schema_version(receipt,(DELIVERY_RECEIPT_VERSION,),owner='Provider delivery receipt')
    for field,version in [('usage_facts_projection',USAGE_FACTS_VERSION),('delivery_receipt_projection',DELIVERY_RECEIPT_VERSION)]:
        if row.get(field) is not None:require_schema_version(row[field],(version,),owner='Provider metadata header '+field)
    return row


def usage_facts_projection(value):
    """Bounded header view for model/human/analytics without resolving observation bodies."""
    if not isinstance(value,dict):return None
    validate_provider_metadata({'usage_facts':value})
    return json.loads(json.dumps({key:value.get(key) for key in ('schema_version','attempt_id','logical_turn_id','provider',
        'native_binding_id','native_turn_id','selected','baseline','reset_epoch','coverage','model_observations')}))


def delivery_receipt_projection(value):
    if not isinstance(value,dict):return None
    validate_provider_metadata({'delivery_receipt':value})
    return json.loads(json.dumps({key:value.get(key) for key in ('schema_version','provider','app_semantic_digest','parts',
        'channels','request_fingerprints','request_fingerprint_basis','native_inventory','platform_extra_instructions','provider_retention')}))
