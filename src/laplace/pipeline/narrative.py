"""Stage D — the narrative specification (rebuild mandate §7).

The resolved structure fixes the intellectual order; this stage fixes the
explanatory journey as PARAGRAPH PLANS — one JSON file per section under
``<manuscript_dir>/narrative/<sid>.json``:

    {"section_id": ..., "paragraphs": [schema.PARAGRAPH_FIELDS records]}

This artifact REPLACES the retired section briefs as the prose-driving
artifact. Nothing substantive is left for the prose realiser to decide: every
paragraph carries its function, proposition, inputs, anchors, qualification
and connections. :func:`validate_narrative` is the §7.2 gate;
:func:`narrative_packet` assembles the CLOSED packet the prose stage receives
(mandate §13 context isolation — the packet, the registries, nothing else;
the voice profile is joined by the dispatch compiler, never stored here).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from laplace.pipeline import pathsafe, projection_spec, registry, schema, structural


def narrative_dir(project: str, repo_root: Path | None = None) -> Path | None:
    proj = registry.resolve(project, repo_root=repo_root)
    return proj.stage_path("narrative", repo_root) if proj else None


# ---------------------------------------------------------------------------
# THE AUTHOR-ARCHITECTURE PROFILE (architecture-profile-consumed, W-arch).
# The narrative planners at the storyboard stage CONSUME profiles/author_architecture.yaml
# — his whole-paper structural grain (how he opens, ladders, orders, places figures, and
# closes). A profile nothing reads is a prose doc that rots (his charge); this is the
# consuming edge, in code. Refs-only + field summaries — the planner packets carry HOW he
# writes without inlining the whole derivation, composing WITH the conceptric content
# (never overriding it as the content source). Additive: no file → None → no channel → the
# packet is byte-identical to pre-wire.
# ---------------------------------------------------------------------------

#: the profile lives here; the string is the consuming edge the clause verifier probes.
ARCHITECTURE_PROFILE_PATH = "profiles/author_architecture.yaml"


MAX_ARCHITECTURE_BYTES = 64 * 1024
MAX_ARCHITECTURE_FIELDS = 64


def architecture_content_contract() -> dict:
    """The serialized document contract shared by profile help, reads and editors."""
    summary = {'type': 'string', 'minLength': 1, 'pattern': r'\S',
               'description': 'Nonempty preference summary, at most 8000 UTF-8 bytes.'}
    schema = {'type': 'object', 'required': ['profile'], 'properties': {
        'profile': {'type': 'object', 'minProperties': 1, 'maxProperties': MAX_ARCHITECTURE_FIELDS,
            'propertyNames': {'type': 'string', 'minLength': 1, 'maxLength': 200},
            'additionalProperties': {'type': 'object', 'required': ['summary'], 'properties': {
                'summary': summary, 'evidence': {'type': ['object', 'null'], 'properties': {
                    'observation': {'type': 'string'},
                    'sources': {'type': 'array', 'maxItems': 64, 'items': {'type': 'string'}}}}}}}}}
    return {'schema_version': 'laplace.architecture-profile-content/1', 'format': 'JSON-compatible YAML or JSON',
        'document_schema': schema,
        'example': {'profile': {'narrative_arc': {'summary': 'Describe the intended explanatory sequence.'}}},
        'starter': {'profile': {'narrative_arc': {'summary': ''}}},
        'delivery': architecture_delivery_contract(),
        'limits': {'stored_utf8_bytes': MAX_ARCHITECTURE_BYTES, 'summary_utf8_bytes': 8000},
        'instruction': 'Serialize the complete document under change.content. Each named field belongs inside profile and requires its own summary. Preserve existing fields and qualifications; generated text never confirms authorship.'}


def _architecture_shape_error() -> str:
    contract = architecture_content_contract()
    return ('Architecture profile requires 1..64 named summary fields inside profile; '
            'change.content is serialized YAML/JSON, for example ' + json.dumps(contract['example']) +
            '. Inspect the profile read content_contract or profile_change help; preserve existing fields.')


def architecture_document(content: str, *, max_input_bytes: int = MAX_ARCHITECTURE_BYTES) -> dict:
    """Validate the actual workspace profile, without interpreting prose as authority."""
    import yaml
    if not isinstance(content, str) or not content.strip() or len(content.encode()) > max_input_bytes:
        raise ValueError('Architecture profile requires bounded nonempty YAML/JSON content.')
    try:
        if any(isinstance(token, yaml.tokens.AliasToken) for token in yaml.scan(content)):
            raise ValueError('Architecture profiles use explicit values; YAML aliases are not supported.')
        data = yaml.safe_load(content)
        json.dumps(data, ensure_ascii=False)
    except (yaml.YAMLError, RecursionError, TypeError) as error:
        raise ValueError('Architecture profile requires bounded JSON-compatible YAML values.') from error
    from jsonschema import Draft202012Validator
    issue = next(Draft202012Validator(architecture_content_contract()['document_schema']).iter_errors(data), None)
    if issue:
        raise ValueError(_architecture_shape_error())
    for value in data['profile'].values():
        if len(value['summary'].encode()) > 8000:
            raise ValueError('Each architecture field summary is bounded to 8000 UTF-8 bytes.')
    return data


def architecture_summary_digest(summary: str) -> str:
    import hashlib
    return 'sha256:' + hashlib.sha256(' '.join(summary.split()).encode()).hexdigest()


def architecture_field_digest(value: dict) -> str:
    """Pin the complete field, including evidence/qualifications beside its summary."""
    import hashlib
    normalized = {**value, 'summary': ' '.join(value['summary'].split())}
    return 'sha256:' + hashlib.sha256(json.dumps(normalized, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _architecture_confirmation(root: Path, data: dict, fields: dict) -> dict:
    """Resolve one exact existing decision; generated status/summary strings confer nothing."""
    ref = data.get('author_confirmation')
    if not isinstance(ref, dict) or set(ref) != {'id', 'project'}:
        return {}
    try:
        from laplace.writing import records
        row = records.selected_journal_fields(ref['project'], ref['id'], root,
            fields=['record', 'decision', 'profile_path', 'profile_scope', 'actor', 'confirmed_fields'])
    except (ValueError, OSError, KeyError):
        return {}
    if (row.get('record') != 'writing-proposal-decision' or row.get('decision') != 'confirm-profile'
            or row.get('profile_path') != ARCHITECTURE_PROFILE_PATH or row.get('profile_scope') != 'workspace'
            or (row.get('actor') or {}).get('kind') != 'human'):
        return {}
    return {name: {'id': ref['id'], 'project': ref['project']}
            for name, value in fields.items() if (row.get('confirmed_fields') or {}).get(name)
            == architecture_field_digest(data['profile'][name])}


def architecture_status(repo_root: Path | None = None, *, include_content=False) -> dict:
    """Bounded structural-form prior identity, separate from voice and reader truth.

    Summary reads retain no profile body. Exact reads expose the existing field
    summaries, while absent/invalid/refused inputs remain explicit unavailable state.
    """
    import hashlib
    root = Path(repo_root).resolve() if repo_root is not None else registry._repo_root().resolve()
    path = root / ARCHITECTURE_PROFILE_PATH
    result = {'family': 'architecture', 'scope': 'workspace',
              'purpose': 'Structural and narrative form prior; not scientific evidence or authored reader expectations.',
              'source': {'path': ARCHITECTURE_PROFILE_PATH, 'origin': 'repository'},
              'profile_revision': None, 'field_refs': [], 'editable': True,
              'edit_reason': 'Workspace structural preferences use the guarded profile candidate owner.',
              'read_more': {'operation': 'structure', 'payload': {'view': 'architecture-profile'}},
              'currentness_basis': 'Current profile bytes only; no scientific acceptance or reader comprehension is asserted.'}
    fields = {}
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        result.update(status='REFUSED', reason='Architecture profile must be a regular workspace-owned file.')
    elif not path.exists():
        result.update(status='ABSENT', reason='This workspace has no recorded architecture prior; authored reader contracts remain available.')
    elif not path.is_file():
        result.update(status='REFUSED', reason='Architecture profile is not a regular file.')
    else:
        try:
            with path.open('rb') as stream:
                raw = stream.read(MAX_ARCHITECTURE_BYTES + 1)
            if len(raw) > MAX_ARCHITECTURE_BYTES:
                result.update(status='REFUSED', reason='Architecture profile exceeds the 64KiB read bound.')
            else:
                result['profile_revision'] = 'sha256:' + hashlib.sha256(raw).hexdigest()
                data = architecture_document(raw.decode('utf-8'))
                profile = data['profile']
                for name, value in profile.items():
                    if (not isinstance(name, str) or not name or len(name) > 200
                            or not isinstance(value, dict) or not isinstance(value.get('summary'), str)
                            or not value['summary'].strip()):
                        raise ValueError('Each architecture field requires a nonempty text summary.')
                    summary = ' '.join(value['summary'].split())
                    assertion_text = summary + ' ' + str((value.get('evidence') or {}).get('observation') or '')
                    historical = any(marker in assertion_text.lower() for marker in
                                    ('confirmed-his', 'his correction', 'confirmed-corrected'))
                    fields[name] = {'summary': summary, 'confirmed_his': False,
                                    'field_revision': architecture_field_digest(value),
                                    'historical_confirmation_assertion': historical,
                                    'ref': f'{ARCHITECTURE_PROFILE_PATH}#profile.{name}'}
                confirmations = _architecture_confirmation(root, data, fields)
                for name, ref in confirmations.items():
                    fields[name].update(confirmed_his=True, author_confirmation=ref)
                result.update(status='AVAILABLE', reason='Current workspace architecture prior loaded.',
                              field_refs=[{'id': name, 'ref': value['ref']} for name, value in fields.items()])
        except OSError:
            result.update(status='INVALID', reason='Architecture profile bytes are unavailable.')
        except (UnicodeError, ValueError) as error:
            result.update(status='INVALID', reason=str(error))
        except Exception as error:
            # Safe YAML parse exceptions and unavailable parser do not become valid emptiness.
            result.update(status='INVALID', reason='Architecture profile could not be parsed: ' + type(error).__name__)
    result['currentness'] = 'CURRENT' if result['status'] == 'AVAILABLE' else 'UNAVAILABLE'
    result['editable'] = result['status'] in {'AVAILABLE', 'ABSENT'} or (
        result['status'] == 'INVALID' and result['profile_revision'] is not None)
    # Source custody and consumed form are distinct: comments/metadata outside
    # the effective summary projection do not reopen reader obligations.
    identity = {key: result[key] for key in ('status', 'scope', 'source')}
    identity['fields'] = fields if result['status'] == 'AVAILABLE' else {}
    result['revision'] = 'sha256:' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    if include_content and result['status'] == 'AVAILABLE':
        result['fields'] = fields
    return result


def update_architecture_profile(content: str, expected_revision: str | None, repo_root: Path,
                                *, author_confirmation: dict | None = None) -> dict:
    """The only workspace architecture writer, guarded by exact current file bytes.

    Candidate content cannot mint authority. Keep a previous decision reference
    only for unchanged summaries; the loader verifies every field against it.
    """
    import uuid
    import yaml
    from filelock import FileLock
    root = Path(repo_root).resolve()
    path = root / ARCHITECTURE_PROFILE_PATH
    data = architecture_document(content, max_input_bytes=4 * MAX_ARCHITECTURE_BYTES)
    data.pop('author_confirmation', None)
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + '.lock'):
        before = architecture_status(root, include_content=True)
        if before['status'] not in {'AVAILABLE', 'ABSENT'} and not (
                before['status'] == 'INVALID' and before['profile_revision']):
            raise ValueError('Architecture profile is unavailable; repair its recorded input before applying a candidate.')
        if before['profile_revision'] != expected_revision:
            raise ValueError('CHANGED_INPUT: architecture profile revision conflict; the candidate is retained.')
        if author_confirmation is not None:
            data['author_confirmation'] = author_confirmation
        elif path.is_file() and before['status'] == 'AVAILABLE':
            previous = architecture_document(path.read_text(encoding='utf-8'))
            if isinstance(previous.get('author_confirmation'), dict):
                data['author_confirmation'] = previous['author_confirmation']
        raw = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        architecture_document(raw)
        pending = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
        pending.write_text(raw, encoding='utf-8')
        pending.replace(path)
    return architecture_status(root, include_content=True)


def architecture_profile(repo_root: Path | None = None) -> dict[str, Any] | None:
    """Legacy field projection for dispatch/taste callers; structured reads use architecture_status.

    Keep this compatibility shape until those external field consumers migrate.
    Unavailable states stay explicit in the current status/read and native context.
    """
    observed = architecture_status(repo_root, include_content=True)
    return observed.get('fields') if observed['status'] == 'AVAILABLE' else None


def architecture_section_field_ids(position: int | None, n_sections: int | None,
                                   job: str | None, bears_derivation: bool) -> list[str]:
    """The existing conditional section selector, also used to publish its palette."""
    job_l = (job or "").lower()
    want: list[str] = ["narrative_arc", "register_markers_structural"]
    is_first = (position == 0) or "introduce" in job_l or "motivat" in job_l
    is_last = ((n_sections is not None and position is not None
                and position == n_sections - 1)
               or "conclude" in job_l or "future" in job_l or "outlook" in job_l
               or "synthes" in job_l)
    if is_first:
        want.append("introduction_shape")
    if is_last:
        want.append("conclusion_posture")
    if not is_first and not is_last:
        want.append("section_rhythm")
    # the derivation axis: his two confirmed-his corrections ride EVERY derivation-bearing
    # section — section_rhythm (derivations made explicitly in appendices) and
    # derivation_granularity (compression licensed only by an apposite citation).
    if bears_derivation or "deriv" in job_l or "prove" in job_l:
        for f in ("section_rhythm", "derivation_granularity"):
            if f not in want:
                want.append(f)
    return want


def architecture_delivery_contract() -> dict:
    """Describe real consumer coverage without widening section delivery."""
    cases = [('Opening', 0, 'Introduce', False), ('Body', 1, '', False),
             ('Closing', 2, 'Conclude', False), ('Derivations', 1, 'Derive', True)]
    palette = {}
    for label, position, job, derivation in cases:
        for name in architecture_section_field_ids(position, 3, job, derivation):
            palette.setdefault(name, {'id': name, 'label': name.replace('_', ' '), 'contexts': []})['contexts'].append(label)
    return {'whole_paper': 'Every field guides whole-paper structure planning.',
        'sections': 'Listed fields guide relevant sections by position, job and derivation needs. Custom fields remain whole-paper preferences.',
        'taste': 'All fields are eligible for taste retrieval; selection is not guaranteed.',
        'section_fields': list(palette.values())}


def architecture_brief_for_section(profile: dict[str, Any] | None, position: int | None,
                                   n_sections: int | None, job: str | None,
                                   bears_derivation: bool) -> dict[str, Any] | None:
    """Select the existing section form prior; confirmation qualifies attribution only."""
    if not profile:
        return None
    want = architecture_section_field_ids(position, n_sections, job, bears_derivation)
    fields = {f: profile[f] for f in want if f in profile}
    if not fields:
        return None
    corrections = [f"{f}: {v['summary']}" for f, v in fields.items() if v["confirmed_his"]]
    return {"ref": ARCHITECTURE_PROFILE_PATH,
            "for": {"position": position, "of": n_sections, "job": job or None,
                    "bears_derivation": bool(bears_derivation)},
            "fields": {f: {"summary": v["summary"], "confirmed_his": v["confirmed_his"],
                           "historical_confirmation_assertion": v.get('historical_confirmation_assertion', False),
                           **({'author_confirmation': v['author_confirmation']} if v.get('author_confirmation') else {}),
                           "ref": v["ref"]} for f, v in fields.items()},
            "his_corrections": corrections}


def load_section(project: str, sid: str, repo_root: Path | None = None) -> dict | None:
    nd = narrative_dir(project, repo_root)
    p = (nd / f"{pathsafe.encode_sid_for_path(sid)}.json") if nd else None
    if p is None or not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # p.is_file() above already confirmed the file exists - corrupt is not absent
        logging.getLogger(__name__).warning(
            "load_section: %s exists but failed to parse: %s", p, exc)
        return None


def write_section(project: str, sid: str, spec: dict,
                  repo_root: Path | None = None) -> Path:
    nd = narrative_dir(project, repo_root)
    nd.mkdir(parents=True, exist_ok=True)
    p = nd / f"{pathsafe.encode_sid_for_path(sid)}.json"
    p.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n",
                 encoding="utf-8")
    return p


def validate_narrative(project: str, sid: str,
                       repo_root: Path | None = None) -> dict[str, Any]:
    """§7.2 — narrative coherence, mechanical:

    - every node in the section's pinned order is an input to ≥1 paragraph;
    - every paragraph has a distinct, non-empty function and a proposition;
    - equation anchors resolve in the effective equation ledger and figure
      anchors in the section's planned figures;
    - connections chain (interior paragraphs name both neighbours);
    - a paragraph never inputs a node the reader has not met (introduced in
      this section or an earlier one — the reader-state join).
    """
    proj = registry.resolve(project, repo_root=repo_root)
    if proj is None:
        return {"pass": None, "error": f"unknown project {project!r}"}
    plan = proj.read_plan(repo_root) or {}
    sec = next((s for s in schema.plan_sections(plan) if s.get("id") == sid), None)
    if sec is None:
        return {"pass": False, "error": f"section {sid!r} not in plan"}
    nspec = load_section(project, sid, repo_root)
    if nspec is None:
        return {"pass": False, "missing": f"narrative/{pathsafe.encode_sid_for_path(sid)}.json"}

    paragraphs = nspec.get("paragraphs") or []
    issues: list[dict[str, str]] = []
    identities = [row.get('paragraph_id') for row in paragraphs]
    if any(not isinstance(ident, str) or not ident for ident in identities) or len(set(str(ident) for ident in identities)) != len(identities):
        issues.append({'kind': 'paragraph-identity', 'reason': 'Paragraph IDs must be explicit unique strings; ordinal fallback is not persistent identity.'})
    planned = set(schema.section_nodes(sec))
    covered: set[str] = set()
    functions: set[str] = set()

    ledger = projection_spec.effective_equation_ledger(project, repo_root)
    figures = set(sec.get("figures") or [])
    state = structural.compute_reader_state(project, repo_root, write=False)["nodes"]
    sec_order = [s["id"] for s in schema.plan_sections(plan)]
    here = sec_order.index(sid)

    for i, para in enumerate(paragraphs):
        pid = para.get("paragraph_id") or f"{sid}-p{i + 1}"
        if not para.get("function"):
            issues.append({"where": pid, "issue": "empty function"})
        elif para["function"] in functions:
            issues.append({"where": pid, "issue": "duplicate paragraph function"})
        else:
            functions.add(para["function"])
        if not para.get("proposition"):
            issues.append({"where": pid, "issue": "empty proposition"})
        for nid in para.get("input_nodes") or []:
            covered.add(nid)
            intro = (state.get(nid) or {}).get("introduced")
            if intro and sec_order.index(intro) > here:
                issues.append({"where": pid,
                               "issue": f"inputs {nid} introduced later ({intro})"})
        anchor = para.get("equation_anchor")
        if anchor and anchor not in ledger:
            issues.append({"where": pid, "issue": f"equation anchor {anchor!r} "
                                                  "not in the equation ledger"})
        fanchor = para.get("figure_anchor")
        if fanchor and fanchor not in figures:
            issues.append({"where": pid, "issue": f"figure anchor {fanchor!r} "
                                                  "not planned in this section"})
        if 0 < i and not para.get("from_previous"):
            issues.append({"where": pid, "issue": "no connection from previous"})
        if i < len(paragraphs) - 1 and not para.get("to_next"):
            issues.append({"where": pid, "issue": "no connection to next"})

    for nid in sorted(planned - covered):
        issues.append({"where": sid, "issue": f"planned node {nid} assigned to "
                                              "no paragraph"})

    return {"pass": not issues, "section": sid, "issues": issues,
            "n_paragraphs": len(paragraphs), "covered": len(covered & planned),
            "planned": len(planned)}


def validate_all(project: str, repo_root: Path | None = None) -> dict[str, Any]:
    proj = registry.resolve(project, repo_root=repo_root)
    plan = (proj.read_plan(repo_root) or {}) if proj else {}
    reports = {sec["id"]: validate_narrative(project, sec["id"], repo_root)
               for sec in schema.plan_sections(plan)}
    return {"pass": all(r.get("pass") for r in reports.values()),
            "sections": reports}


def _contribution_hierarchy_block(rank: Any) -> str:
    """Format ``plan.meta.contribution_rank`` for the narrative packet — the SAME
    authored judgement dispatch.py's kernel carries to node builders, reframed as
    CONTENT rather than policy (mandate §13: the prose realiser rides no kernel
    and no POLICY channel, so this must read as the paper's own contribution
    hierarchy, never as an engine instruction — no 'policy'/'contract' framing).
    The parse is shared via ``schema.contribution_rank_lines``; only the frame
    differs. Empty/None → "" (additive: the packet is byte-identical to today
    when the plan carries no rank)."""
    primary, excluded = schema.contribution_rank_lines(rank)
    if not primary and not excluded:
        return ""
    lines = ["THE PAPER'S CONTRIBUTION HIERARCHY (authored):"]
    lines += primary
    if excluded:
        lines.append("EXCLUDED/exploratory - stay outside these claims: "
                      + "; ".join(excluded))
    lines.append("Weight this section's paragraphs to the ranks their claims "
                  "serve, and hold the exclusions above out of the prose.")
    return "\n".join(lines)


def narrative_packet(project: str, sid: str,
                     repo_root: Path | None = None) -> dict[str, Any] | None:
    """The CLOSED packet the prose realiser receives (mandate §13): the section
    contract, the paragraph plans, the semantic content of every input object
    (essence + equation latex where the ledger carries it), the notation and
    terminology registries, and the section's citation entries. Nothing else —
    no history, no other sections' prose, no engine framing.

    ``plan.meta.contribution_rank`` — the paper's own authored contribution
    hierarchy — is CONTENT, not scaffolding: when the plan carries one, it lands
    once as ``contribution_hierarchy``, phrased as narrative frame (see
    :func:`_contribution_hierarchy_block`), never as kernel/policy text. Absent
    → the key is omitted and the packet is byte-identical to today."""
    proj = registry.resolve(project, repo_root=repo_root)
    if proj is None:
        return None
    nspec = load_section(project, sid, repo_root)
    if nspec is None:
        return None
    contracts = (structural.load_contracts(project, repo_root) or {}).get("sections") or {}
    spec = projection_spec.load_spec(project, repo_root) or {}
    record = spec.get("manuscript") or {}
    ledger = projection_spec.effective_equation_ledger(project, repo_root)

    nodes: dict[str, Any] = {}
    if proj.kind == "conceptric":
        from laplace.research import corpus_ingest as ci
        rr = Path(repo_root) if repo_root else registry._repo_root()
        net = ci.corpus_network(ci.resolve_corpus(rr, project), repo_root=rr,
                                name=project)
        wanted = {nid for para in nspec.get("paragraphs") or []
                  for nid in (para.get("input_nodes") or [])}
        for nid in sorted(wanted):
            nd = net["nodes"].get(nid)
            if nd is None:
                nodes[nid] = {"missing": True}
                continue
            pj = schema.proj_of(nd)
            nodes[nid] = {"kind": nd.get("kind"), "essence": nd.get("essence"),
                          "latex_label": pj.get("latex_label") or ""}

    plan = proj.read_plan(repo_root) or {}
    sec = next((s for s in schema.plan_sections(plan) if s.get("id") == sid), {})
    bib_path = proj.path(proj.bib, repo_root)
    citations: dict[str, str] = {}
    if bib_path and bib_path.is_file():
        entries = schema.bib_entries(bib_path.read_text(encoding="utf-8"))
        citations = {k: entries.get(k, f"@MISSING{{{k}}}")
                     for k in (sec.get("refs") or [])}

    packet = {
        "section_id": sid,
        "contract": contracts.get(sid) or {},
        "paragraphs": nspec.get("paragraphs") or [],
        "objects": nodes,
        "equation_ledger": {k: v for k, v in ledger.items()
                            if (v.get("section") or "") == sid
                            or any((p.get("equation_anchor") == k)
                                   for p in nspec.get("paragraphs") or [])},
        "notation": record.get("notation") or [],
        "terminology": record.get("terminology") or {},
        "citations": citations,
        "genre": record.get("genre") or "white paper",
    }
    # the paper's own contribution hierarchy is CONTENT (his return-path push,
    # 2026-07-13): additive only — absent/malformed rank leaves the packet
    # byte-identical to today.
    hierarchy = _contribution_hierarchy_block((plan.get("meta") or {}).get("contribution_rank"))
    if hierarchy:
        packet["contribution_hierarchy"] = hierarchy
    return packet
