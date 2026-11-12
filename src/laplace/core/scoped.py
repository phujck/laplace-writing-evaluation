"""Scoped progress: what an operation consumes, what it merely consulted, and what stays to review.

One shared rule for actions, their context and their review (core.identity; owners supply the local
conditions). An operation needs only its actual authority and the current basis its effect
consumes; it never needs global completeness.

Roles of one observed input, judged against what the operation recorded when it was prepared:

  authority  who may perform this effect (project, actor, grant). Changed or unavailable: REFUSE.
  target     the exact current source/target the effect writes or replaces. Changed or unavailable: REFUSE.
  consumed   meaning the result rests on (evidence a claim was drawn from, a consumed parent
             constraint, a prerequisite's acceptance). Changed or unavailable: REFUSE; the old result
             is not renewed, rebased or blessed by a later effect.
  consulted  observations used to navigate or witness (a derived PDF, a build or presentation
             status, an earlier view of a page). Changed or unavailable: the effect may proceed, and
             the change becomes a typed LOCAL review obligation on that result.

A result therefore has a grade (``grade``): an applied effect with open obligations is
APPLIED_REVIEW_PENDING, which is not acceptance of every claim it may affect; obligations are
answered by reviewing their subject, never by the effect itself, and an obligation can never be a
precondition of its own closure (``closure_admissible``). Aggregation (``aggregate``) carries only
consumed children into a parent: an independent neighbour's refusal stays local, a consumed child's
pending review stays pending, and nothing resets the whole.

Owners that use this rule: writing.proposal_currentness (generated proposals; read roles from
writing.reads.read_role), writing.reconciliation and writing.document_templates (current-source and
template candidates), writing.reader_restructure / reader_logical_restructure (reader-unit
obligations), project_work (Work containment versus consumed parent meaning) and
project_work_review (review intent). See docs/scoped-progress.md.
"""
from __future__ import annotations

from laplace.core.identity import canonical_digest

ROLES = ('authority', 'target', 'consumed', 'consulted')
REFUSING = frozenset({'authority', 'target', 'consumed'})
OBLIGATION_SCHEMA = 'laplace.scoped-obligation/1'
GRADES = ('REFUSED', 'INCOMPLETE', 'APPLIED_REVIEW_PENDING', 'APPLIED')


def observation(subject, role, *, expected, observed, detail=None) -> dict:
    """One input as recorded (``expected``) and as seen now (``observed``; None means unavailable)."""
    if role not in ROLES:
        raise ValueError('scoped role must be one of ' + ', '.join(ROLES))
    state = 'CURRENT' if observed is not None and observed == expected else 'UNAVAILABLE' if observed is None else 'CHANGED'
    return {'subject': subject, 'role': role, 'state': state, 'expected': expected, 'observed': observed,
            **({'detail': detail} if detail is not None else {})}


def obligation(kind, reason, *, subject=None, basis=None, key=None, **extra) -> dict:
    """A typed local review obligation. ``kind`` and ``reason`` keep the shape every existing reader shows.

    Identity is the reviewed diagnostic itself: kind, the subject it is about, the consumed basis it was judged
    against and its diagnostic ``key`` (the reason text when no stable key is given). The same diagnostic of the
    same subject on a retry or a later phase has the same id and is recorded once; two different unresolved
    reasons never share an id. Producers name one subject form across their phases."""
    if not isinstance(kind, str) or not kind or not isinstance(reason, str) or not reason:
        raise ValueError('An obligation names its kind and reason.')
    row = {'schema': OBLIGATION_SCHEMA, 'kind': kind, 'reason': reason, 'scope': 'local',
           **({'subject': subject} if subject is not None else {}),
           **({'basis': basis} if basis is not None else {}),
           **({'key': key} if key is not None else {}), **extra}
    row['id'] = 'OBL-' + canonical_digest({'kind': kind, 'subject': subject, 'basis': basis,
                                 'diagnostic': key if key is not None else reason}).removeprefix('sha256:')[:24]
    return row


def merge(*groups) -> list:
    """Obligations once each (by id when typed, by content otherwise), in first-seen order."""
    seen, out = set(), []
    for group in groups:
        for row in group or []:
            key = row.get('id') if isinstance(row, dict) and row.get('id') else canonical_digest(row)
            if key not in seen:
                seen.add(key)
                out.append(row)
    return out


def judge(observations) -> dict:
    """Admission of one scoped effect: refusals from authority/target/consumed inputs, obligations from consulted ones."""
    refusals, obligations = [], []
    for row in observations:
        if row['state'] == 'CURRENT':
            continue
        if row['role'] in REFUSING:
            refusals.append(row)
        else:
            obligations.append(obligation('CONSULTED_INPUT_' + row['state'],
                'A consulted observation (' + str(row['subject']) + ') is ' + row['state'].lower()
                + ' since this result was prepared; the effect does not depend on it. Review it against the result.',
                subject=row['subject'], basis=row['expected'], key=row['state'],
                **({'detail': row['detail']} if 'detail' in row else {})))
    return {'admitted': not refusals, 'refusals': refusals, 'obligations': obligations,
            'semantic_currentness': semantic_currentness(obligations)}


def semantic_currentness(obligations) -> str:
    """What a scoped effect asserts about the meaning it touches: nothing, or a named pending review."""
    return 'REVIEW_REQUIRED' if obligations else 'NOT_ASSERTED'


def grade(*, refused=False, complete=True, obligations=()) -> str:
    if refused:
        return 'REFUSED'
    if not complete:
        return 'INCOMPLETE'
    return 'APPLIED_REVIEW_PENDING' if obligations else 'APPLIED'


def aggregate(children) -> dict:
    """A parent's standing from its children: only consumed children count; independent ones stay local.

    ``children`` rows are {'id', 'grade', 'consumed': bool}. The parent is REFUSED/INCOMPLETE only through a
    consumed child, and pending review propagates as pending; nothing else resets it."""
    consumed = [row for row in children if row.get('consumed')]
    independent = [row['id'] for row in children if not row.get('consumed')]
    order = {name: index for index, name in enumerate(GRADES)}
    worst = min((row['grade'] for row in consumed), key=order.__getitem__, default='APPLIED')
    return {'grade': worst, 'by': [row['id'] for row in consumed if row['grade'] == worst and worst != 'APPLIED'],
            'independent_children': independent}


def closure_admissible(obligation_row, closure_basis) -> bool:
    """An obligation closes on reviewed evidence; it can never require its own prior closure."""
    ident = obligation_row.get('id')
    return ident is not None and ident not in set(closure_basis or ())


def consumed_digest(spec, fields) -> str:
    """The identity of only the fields of ``spec`` that a dependent actually consumes."""
    return canonical_digest({key: spec.get(key) for key in sorted(fields)})
