"""Pure document-template request contracts; the source/candidate owner enforces them."""
from __future__ import annotations

import copy

SCHEMA = 'laplace.document-template-candidate/1'
PREVIEW_SCHEMA = 'laplace.template-preview-ref/1'
SHA = {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'}
REF = {'type': 'object', 'required': ['id', 'version'], 'properties': {
    'id': {'type': 'string', 'pattern': '^PROP-[0-9a-f]{32}$'}, 'version': SHA}, 'additionalProperties': False}
MAX_PART = 8000


def preview_schema():
    from laplace.manuscript.build_jobs import schema
    return {'type': 'object', 'required': ['schema_version', 'build_job', 'build_receipt_id', 'observed_input_revision', 'output'],
        'properties': {'schema_version': {'const': PREVIEW_SCHEMA}, 'build_job': {'allOf':[schema(), {'properties':{'target_kind':{'const':'candidate'}}}]},
            'build_receipt_id': {'type': 'string', 'pattern': '^ART-[0-9a-f]{32}$'},
            'observed_input_revision': SHA, 'output': {'type': 'object', 'required': ['file', 'content_revision'],
                'properties': {'file': {'type': 'string', 'minLength': 1}, 'content_revision': SHA}, 'additionalProperties': False}},
        'additionalProperties': False}


def change_contract():
    text = {'type': 'string'}
    edit = {'type': 'object', 'required': ['file', 'line_start', 'line_end', 'before', 'after'],
        'properties': {'file': text, 'line_start': {'type': 'integer', 'minimum': 1},
            'line_end': {'type': 'integer', 'minimum': 1}, 'before': text, 'after': text}, 'additionalProperties': False}
    prepare = {'type': 'object', 'required': ['action', 'guards', 'reason'], 'properties': {
        'action': {'const': 'prepare'}, 'reason': {'type': 'string', 'minLength': 1},
        'guards': {'type': 'object', 'required': ['expected_selection', 'source_guards'],
            'properties': {'expected_selection': SHA, 'source_guards': {'type': 'object', 'minProperties': 1, 'additionalProperties': SHA}},
            'additionalProperties': False},
        'source_edits': {'type': 'array', 'minItems': 1, 'items': {'type': 'object', 'required': ['file', 'content'],
            'properties': {'file': text, 'content': text}, 'additionalProperties': False}},
        'edits': {'type': 'array', 'minItems': 1, 'items': edit},
        'draft_basis': {'type': 'object', 'required': ['file', 'revision'],
            'properties': {'file': text, 'revision': {'type': 'string', 'minLength': 1}}, 'additionalProperties': False},
        'template_sources': {'type': 'array', 'items': {'type': 'object', 'required': ['repository', 'path'],
            'properties': {'repository': text, 'path': text, 'member': text}, 'additionalProperties': False}},
        **{key: {'type': 'array', 'uniqueItems': True, 'items': {'type': 'string', 'pattern': '^READ-[0-9a-f]{32}$'}}
            for key in ('source_read_ids', 'template_read_ids')}},
        'additionalProperties': False, 'oneOf': [
            {'required': ['source_edits'], 'not': {'required': ['edits']}},
            {'required': ['edits'], 'not': {'anyOf': [{'required': ['source_edits']}, {'required': ['draft_basis']}]}}]}
    apply = {'type': 'object', 'required': ['action', 'candidate_ref', 'preview_ref'],
        'properties': {'action': {'const': 'apply'}, 'candidate_ref': REF, 'preview_ref': preview_schema()}, 'additionalProperties': False}
    recover = {'type': 'object', 'required': ['action', 'candidate_ref'], 'properties': {
        'action': {'const': 'recover'}, 'candidate_ref': REF,
        'application_id': {'type': 'string', 'pattern': '^WA-[0-9a-f]{32}$'},
        'application_intent_id': {'type': 'string', 'pattern': '^DEC-[0-9a-f]{32}$'}}, 'additionalProperties': False,
        'oneOf': [{'required': ['application_id'], 'not': {'required': ['application_intent_id']}},
                  {'required': ['application_intent_id'], 'not': {'required': ['application_id']}}]}
    return {'oneOf': [prepare, apply, recover]}


def read_contract():
    return {'type': 'object', 'required': ['view'], 'properties': {
        'view': {'enum': ['template', 'template-candidates']}, 'candidate_ref': REF,
        'preview_ref': preview_schema(), 'part': {'enum': ['metadata', 'original', 'proposed', 'diff', 'closure',
            'diagnostics', 'preview-output', 'preview-image']}, 'file': {'type': 'string'},
        'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': MAX_PART},
        'page': {'type': 'integer', 'minimum': 1}}, 'additionalProperties': False, 'allOf': [
        {'if': {'properties': {'view': {'const': 'template'}}}, 'then': {'required': ['candidate_ref']},
         'else': {'not': {'anyOf': [{'required': [key]} for key in ('candidate_ref', 'preview_ref', 'part', 'file', 'page')]}}},
        {'if': {'required': ['part'], 'properties': {'part': {'enum': ['preview-output', 'preview-image']}}},
         'then': {'required': ['preview_ref'], 'not': {'anyOf': [{'required': [key]} for key in ('file', 'offset', 'limit')]}},
         'else': {'not': {'required': ['page']}}},
        {'if': {'required':['part'],'properties':{'part':{'enum':['original','proposed','diff','closure','diagnostics']}}}, 'then':{'not':{'required':['preview_ref']}}},
        {'if': {'required': ['part'], 'properties': {'part': {'const': 'preview-image'}}},
         'then': {'required': ['page']}, 'else': {'not': {'required': ['page']}}}]}


def document_contract(ordinary):
    return {'oneOf': [copy.deepcopy(ordinary), read_contract()]}
