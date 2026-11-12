"""Recursive Work navigation, the Work action/context descriptor and the observer token; no stored state.

Ownership
  A section of the project_work owner's read side, called only by ``project_work_views.read`` (HTTP
  ``/work/state`` and native ``project`` share it). Truth stays in ``project_work`` (specifications, standing,
  revisions), ``project_work_review`` (review facet, follow-up composition) and ``project_work_activity``
  (qualified execution observations). This module chooses what a navigation read delivers.

One relational pattern at every grade
  A campaign (root Work that contains Work), a branch (contained Work that contains Work) and a task (Work
  that contains none) are the same Work object: each has its own detail, allowed actions, standing and
  descriptor. A parent is never only a folder: its row opens its children (``view:branch``) and inspects
  itself (``view:detail``) as two separate reads.

Qualified standing (``standing``)
  ``group`` is one of attention, active, awaiting, blocked, in-progress, ready, settled; ``facts`` are the
  distinct qualified facts behind it, never merged: observed activity (in-app or external, with source and
  time) is not the declared ``in-progress`` status; a completion whose acceptance is not CURRENT, a pending
  follow-up join, a containment problem and a requested change are ATTENTION even when done; integration is
  only a satisfied ``live`` obligation.

One group at every depth (``view:group``)
  ``group`` names one of GROUPS; the read lists every Work of the read cut whose qualified group is that group, at any
  depth of containment, in the cut's order (``Index.group_ids``, which the attention view also uses), each row the
  attention row (``nav_row`` plus its containment ``path``), paged and held to the page line as attention is. The roots
  view's ``counts.groups`` counts every Work of the project once by its group (non-zero groups only); they sum to
  ``counts.work``.

Rollups (``rollup``)
  Computed over the complete containment subtree in the read cut, never a page: counts by group, the first
  ready descendant in authored order, the attention count and first id. A rollup states what it preserves and
  when a caller must descend.

NAV rows and pages (repair1 WI-R5)
  A navigation row is the NAV projection (``nav_row``): id, qualified id, the title and purpose as whole-character
  UTF-8 previews (TITLE_BYTES, PURPOSE_BYTES) with ``title_complete``/``purpose_complete`` false when cut, grade,
  standing (at most FACTS facts), activity state and the compact rollup. It carries no handles: the page's one
  ``row_reads`` names the detail and branch reads by id. A page holds whole rows only, at most ``limit`` positions, and
  its COMPLETE output as its door emits it fits ``line()`` (CAP, or the smaller line the shared delivery plan gives a
  bounded native read; see THE FINAL-OUTPUT INVARIANT above _compose and writing.delivery). ``pagination.next_read`` continues from the
  first position not covered under the same cut and ``bounded_by`` says which bound ended the page. A position whose row
  cannot fit is covered by an ``oversized`` notice (with its exact id when that fits, else sizes and the identity digest)
  and the page says ``complete: false``; when not even the smallest notice fits beside the page's fixed part the read is
  refused (OutputRefused) naming sizes and view:detail. A branch header's coarse descriptor names its reads through the
  page's ``row_reads`` rather than repeating the identity in every handle.
  Whole values are the detail read.

Order and parallel qualification (``view:branch``)
  Children are ordered over the complete sibling set: authored order, with a sibling's declared prerequisite
  first; a prerequisite cycle keeps authored order and is named. A child's ``parallel`` fact says only what
  the owner knows: none of its own declared prerequisites is open. Conflicts, authority and resources are not
  assessed, and nothing is inferred from a page or from the absence of an edge on it.

The action/context descriptor (``action_context``, D2-E; repair1 WI-R1)
  At every grade: the exact target and its revisions, the read cut, each allowed action BY NAME with the guards it
  consumes, local relationships (parent, contains, needs, affects) with totals, qualifications, and for a parent what
  its summary preserves and when to descend. The action itself (handle, guard, admitted statuses and refusals from
  ``project_work.disposition_policy``, review-phase preparation from ``project_work_review.preparation``, declared
  effects, recovery reads) lives once in ``allowed_actions`` (``project_work_views._actions``), which native callers
  and the human editor/recorder consume. Execution still uses the owner-issued call and its guard.

References and history (repair1 WI-R1)
  ``reference`` resolves a Work in its own project: qualified identity and title (codes stay as authored), location
  (path of at most BREADCRUMBS containing Work, the omitted count and the root), recorded names and counts with the
  ``history`` read, the recorded follow-up origin and follow-ups. ``view:history`` pages every specification row
  (with what changed), standing change and review phase of one Work under the read cut.

The observer token (``observe``, D2-B)
  An unchanged poll (``since`` equal to the token) returns only the token and any next expiry. Detail, roots and
  branch reads carry ``observe_basis``, the components they consumed, so an observer compares its first token with
  what is mounted. ``wo1.<records>.<selected>.<activity>``: the project's semantic Work records (specifications and phase
  identities), the selected Work's records and the qualified activity basis (including expiry, a read-time
  comparison), all three from one captured owner fold (``project_work._captured``), so a ledger above the owner's
  retention cap is read whole, never as absence. The ledger stat identity only invalidates the owner cache; an unrelated project's append
  returns the same token. With a ``since`` token of the same version the response names which components
  differ; otherwise the change is a coarse "may have changed". It is a hint for bounded owner re-reads, never
  a guard or evidence witness.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import threading

from laplace.work import project_work as work

GROUPS = ('attention', 'active', 'awaiting', 'blocked', 'in-progress', 'ready', 'settled')
NAV_PAGE = 12
ATTENTION_PREVIEW = 6
BREADCRUMBS = 12
CAP = 30000                # the retained page line: the WHOLE output of a navigation read as its door emits it
PROJECTION_OWNER = 'project_work_navigation.page'   # the projection this owner reports to writing.delivery
ID_INLINE_BYTES = 1024     # an oversized row's notice carries the exact id when the id itself is at most this long
ATTENTION_BYTES = 6000    # the attention preview inside roots page one
TITLE_BYTES = 480         # NAV previews; the whole values are the detail read
PURPOSE_BYTES = 240
PREVIEW_BYTES = 120
FACTS = 3
TOKEN_VERSION = 'wo1'
POLL = {'after_ms': 5000, 'max_ms': 60000, 'backoff': 2, 'hidden': 'pause', 'destroyed': 'stop'}

_TOKEN_CACHE: dict = {}
_TOKEN_LOCK = threading.Lock()


# ---------------------------------------------------------------------------------------------- standing

def _fact(code, text):
    return {'code': code, 'text': text}


def standing(row, activity=None) -> dict:
    """The qualified standing of one resolved Work row (see the module text)."""
    life = row.get('lifecycle') or {};acceptance = row.get('current_acceptance') or {};review = row.get('review') or {}
    facts, attention = [], []
    if activity:
        state = activity['state']
        if activity['active']:
            facts.append(_fact('observed-' + state, ('%s (%s)' % (state.capitalize(), 'in-app' if activity['source'] == 'in-app' else 'external, attested'))))
        elif state == 'unknown':
            facts.append(_fact('activity-unknown', 'Activity unknown: the last observation expired or was lost'))
        else:
            facts.append(_fact('observed-' + state, 'External actor reported %s; the Work is not completed by it' % state))
    if row.get('task_kind') == 'session-request' and not life.get('closed'):
        facts.append(_fact('requested', 'Requested (queued session request)'))
    if row.get('recorded_status') == 'in-progress':
        facts.append(_fact('declared-in-progress', 'Marked in progress (declared, not observed)'))
    if life.get('completed'):
        status = acceptance.get('status')
        if status == 'CURRENT':
            facts.append(_fact('done-current', 'Done; acceptance current'))
        else:
            attention.append(_fact('done-' + str(status or 'UNKNOWN').lower().replace('_', '-'),
                                   'Done; acceptance %s' % str(status or 'UNKNOWN').lower().replace('_', ' ')))
    elif life.get('closed'):
        facts.append(_fact(str(row.get('recorded_status')), 'Closed as %s' % row.get('recorded_status')))
    for item in review.get('obligations') or ():
        if item.get('status') in {'HOLD', 'REJECTED'} and item.get('currentness') == 'CURRENT' and not life.get('closed'):
            attention.append(_fact('changes-requested', 'Changes requested: ' + str(item.get('label'))[:80]));break
    if review.get('pending_joins'):
        attention.append(_fact('pending-join', 'Follow-up join pending recovery'))
    for item in review.get('obligations') or ():
        if item.get('scope') == 'live' and item.get('satisfied'):
            # a satisfied live-scope review, named with its exact obligation and review record; it does not by itself
            # establish which code is deployed
            facts.append({**_fact('integrated', 'Live-scope review accepted (obligation %s)' % item['id']),
                          'obligation_id': item['id'], 'review_id': item.get('review_id')})
    if row.get('containment_issue'):
        attention.append(_fact('containment', 'Containing goal unavailable or cyclic'))
    blocked = row.get('blocked_by') or []
    awaiting = None
    if not life.get('closed') and review.get('remaining'):
        kind = (review.get('next') or {}).get('kind')
        if kind in {'handoff', 'review', 'synthesis'}:
            awaiting = _fact('awaiting-' + kind, {'handoff': 'Awaiting handoff for review', 'review': 'Awaiting review',
                                                  'synthesis': 'Awaiting synthesis'}[kind])
            facts.append(awaiting)
    if row.get('status') == 'blocked' and not life.get('completed'):
        if 'cycle' in blocked:
            attention.append(_fact('cycle', 'Prerequisite cycle'))
        elif row.get('recorded_status') == 'blocked':
            facts.append(_fact('held', 'Held: ' + str(row.get('blocked_reason') or 'no recorded reason')[:80]))
        elif any(item not in {'evidence', 'containment', 'cycle'} for item in blocked):
            facts.append(_fact('blocked-prerequisite', 'Waiting on %d prerequisite%s' % (
                sum(item not in {'evidence', 'containment', 'cycle'} for item in blocked),
                '' if sum(item not in {'evidence', 'containment', 'cycle'} for item in blocked) == 1 else 's')))
    if attention:
        group = 'attention'
    elif activity and activity['active']:
        group = 'active'
    elif awaiting:
        group = 'awaiting'
    elif life.get('closed'):
        group = 'settled'
    elif row.get('status') == 'blocked':
        group = 'blocked'
    elif row.get('status') == 'in-progress':
        group = 'in-progress'
    else:
        group = 'ready'
        facts.append(_fact('ready', 'Ready'))
    return {'group': group, 'facts': attention + facts}


# ---------------------------------------------------------------------------------------------- index

class Index:
    """One read cut's containment/prerequisite index (built once per read by project_work_views.read)."""

    def __init__(self, resolved, children, dependants, activity, *, project=None, mode='human', root=None, read_context=None, records=None):
        self.by_id = {row['id']: row for row in resolved}
        self.order = {row['id']: position for position, row in enumerate(resolved)}
        self.children, self.dependants, self.activity = children, dependants, activity
        self.project, self.mode, self.root, self.read_context, self.records = project, mode, root, read_context, records
        self._standing: dict = {}
        self._rollup: dict = {}
        self._actions: dict = {}

    def actions(self, ident):
        """The one allowed-actions carrier of a Work (project_work_views._actions), computed once per read."""
        from laplace.work import project_work_views as views
        if ident not in self._actions:
            self._actions[ident] = views._actions(self.by_id[ident], self.project, self.mode, by_id=self.by_id, root=self.root,
                                                  read_context=self.read_context)
        return self._actions[ident]

    def group_ids(self, group):
        """Every Work of the read cut whose qualified group is ``group``, at any depth, in the cut's order."""
        return [ident for ident in self.by_id if self.standing(ident)['group'] == group]

    def attention_ids(self):
        return self.group_ids('attention')

    def group_counts(self):
        """Every Work of the read cut counted once by its group; non-zero groups only (the rollup convention)."""
        counts = {name: 0 for name in GROUPS}
        for ident in self.by_id:
            counts[self.standing(ident)['group']] += 1
        return {name: count for name, count in counts.items() if count}

    def observe_basis(self, selected=None):
        """The observer token components this read consumed, so an observer's first token is compared with what was shown."""
        from laplace.work import project_work_views as views
        value = {'records': (self.records or '')[7:19], 'activity': views._hash(self.activity['basis'])[7:19]}
        if selected is not None:
            value['selected'] = selected
        return value

    def standing(self, ident):
        if ident not in self._standing:
            self._standing[ident] = standing(self.by_id[ident], self.activity['by_work'].get(ident))
        return self._standing[ident]

    def roots(self):
        return [ident for ident, row in self.by_id.items()
                if not row.get('parent_work_id') or row.get('containment_issue')]

    def ancestors(self, ident):
        trail, seen, parent = [], {ident}, self.by_id[ident].get('parent_work_id')
        while parent and parent in self.by_id and parent not in seen:
            trail.append(parent);seen.add(parent);parent = self.by_id[parent].get('parent_work_id')
        return list(reversed(trail)), bool(parent and parent in seen)

    def descendants(self, ident):
        """Every Work contained below ident in authored order (cycle-safe pre-order)."""
        out, seen, stack = [], {ident}, list(reversed(self.children.get(ident) or []))
        while stack:
            current = stack.pop()
            if current in seen or current not in self.by_id:
                continue
            seen.add(current);out.append(current)
            stack.extend(reversed(self.children.get(current) or []))
        return out

    def rollup(self, ident):
        if ident in self._rollup:
            return self._rollup[ident]
        below = self.descendants(ident)
        groups = {name: 0 for name in GROUPS}
        ready = None;attention_ids = []
        for current in below:
            group = self.standing(current)['group'];groups[group] += 1
            if group == 'ready' and ready is None and not self.children.get(current) and not (self.by_id[current].get('planning') or {}).get('deferred'):
                ready = current
            if group == 'attention':
                attention_ids.append(current)
        value = {'descendants': len(below), 'groups': {key: count for key, count in groups.items() if count},
                 'next': {'id': ready, 'title': self.by_id[ready].get('title')} if ready else None,
                 'attention_ids': attention_ids, 'coverage': 'complete containment subtree at this read cut'}
        self._rollup[ident] = value
        return value

    def sibling_order(self, ids):
        """Authored order with a sibling's declared prerequisite first; (order, cyclic ids)."""
        if any('planning' in self.by_id[ident] for ident in ids):
            from laplace.work.backlog import preferred
            ordered=[row['id'] for row in preferred([self.by_id[ident] for ident in ids])]
            # The original algorithm below still diagnoses cycles independently.
            _saved_order=ordered
        else:_saved_order=None
        members, position = set(ids), {ident: index for index, ident in enumerate(ids)}
        degree, after = {ident: 0 for ident in ids}, {ident: [] for ident in ids}
        for ident in ids:
            for dep in dict.fromkeys(self.by_id[ident].get('depends_on') or []):
                if dep in members and dep != ident:
                    degree[ident] += 1;after[dep].append(ident)
        ready = [(position[ident], ident) for ident in ids if degree[ident] == 0];heapq.heapify(ready);order = []
        while ready:
            _, ident = heapq.heappop(ready);order.append(ident)
            for nxt in after[ident]:
                degree[nxt] -= 1
                if degree[nxt] == 0:
                    heapq.heappush(ready, (position[nxt], nxt))
        placed = set(order);cyclic = [ident for ident in ids if ident not in placed]
        return (_saved_order if _saved_order is not None else order + cyclic), cyclic


# ---------------------------------------------------------------------------------------------- rows

def _grade(index, ident):
    if not index.children.get(ident):
        return 'task'
    row = index.by_id[ident]
    return 'campaign' if not row.get('parent_work_id') or row.get('containment_issue') else 'branch'


def _clip(text, limit):
    """A whole-character prefix of at most ``limit`` UTF-8 bytes and whether it is the complete value."""
    text = ' '.join(str(text or '').split())
    raw = text.encode('utf-8')
    if len(raw) <= limit:
        return text, True
    return raw[:limit - 3].decode('utf-8', 'ignore').rstrip() + '…', False


def _size(value) -> int:
    """Bytes as both doors serialise (json.dumps ensure_ascii=False, default separators; UTF-8)."""
    return len(json.dumps(value, ensure_ascii=False).encode('utf-8'))


def _standing_summary(standing_value):
    return {'group': standing_value['group'], 'facts': standing_value['facts'][:FACTS]}


def nav_row(index, ident, project) -> dict:
    """The NAV projection of one Work (see the module text): identity, the title and purpose as bounded previews with
    their completeness, grade, compact standing, activity state and the compact subtree rollup. Whole values (goal, every
    fact and qualification) are the detail read; a row never carries handles, the page's row_reads do."""
    row = index.by_id[ident]
    title, title_whole = _clip(row.get('title') or ident, TITLE_BYTES)
    purpose, purpose_whole = _clip(row.get('goal'), PURPOSE_BYTES)
    item = {'id': ident, 'qualified_id': project + '::' + ident, 'title': title, 'task_kind': row.get('task_kind'), 'status': row.get('status'),
            'grade': _grade(index, ident), 'child_count': len(index.children.get(ident) or []), 'purpose': purpose,
            'standing': _standing_summary(index.standing(ident))}
    if not title_whole:
        item['title_complete'] = False
    if not purpose_whole:
        item['purpose_complete'] = False
    if row.get('parent_work_id'):
        item['parent_work_id'] = row['parent_work_id']
    activity = index.activity['by_work'].get(ident)
    if activity:
        item['activity'] = {'state': activity['state'], 'source': activity['source']}
    if item['child_count']:
        rollup = index.rollup(ident)
        item['rollup'] = {'descendants': rollup['descendants'], 'groups': rollup['groups'],
                          'next': ({'id': rollup['next']['id'], 'title': _clip(rollup['next']['title'], PREVIEW_BYTES)[0]} if rollup['next'] else None),
                          'attention': len(rollup['attention_ids']), 'first_attention': rollup['attention_ids'][:1]}
    return item


def relation_row(index, ident, project) -> dict:
    """A detail relation row (requires/children/dependants): LIST row with its qualified standing."""
    from laplace.work import project_work_views as views
    item = views._public(index.by_id[ident], project)
    item['child_count'] = len(index.children.get(ident) or [])
    item['standing'] = index.standing(ident)
    return item


def row_reads(project) -> dict:
    """The one owner read per row kind of a navigation page (rows carry ids, not copies of handles)."""
    from urllib.parse import urlencode
    return {'id_param': 'id',
            'detail': {'operation': 'project', 'payload': {'namespace': project, 'view': 'detail'},
                       'http': {'method': 'GET', 'url': '/work/state?' + urlencode({'project': project, 'view': 'detail'})}},
            'branch': {'operation': 'project', 'payload': {'namespace': project, 'view': 'branch'},
                       'http': {'method': 'GET', 'url': '/work/state?' + urlencode({'project': project, 'view': 'branch'})}},
            'says': 'Add id=<row id> to read one row exactly; branch opens a row that contains Work.'}


# THE FINAL-OUTPUT INVARIANT (repair3 WI-R5b-R1). Every navigation read (roots, branch, attention, group and the attention
# preview) is composed by _compose as its COMPLETE output and verified with emitted(), the bytes its door actually emits,
# against line(): CAP, or the smaller line the shared delivery plan gives a bounded native read (writing.delivery: the
# declared bound minus the door's exact review_read and read_receipt, measured from the composers that write them). The
# projection chosen (line, positions covered, row/notice/digest per position) is reported to the plan and retained by the
# read receipt; a pure replay rebuilds exactly that projection, so only a genuine owner change alters its digest.
# Why a result cannot pass the line: (1) at most `limit` positions are tried once each, the first by an exact one-item
# composition, later ones by a running estimate (a later row that does not fit starts the next page); (2) the composed
# output is then measured whole and the last item dropped while more than one remains (at most `limit` drops); (3) a single remaining
# item is demoted at most twice (row -> notice with its exact id -> notice with only sizes and the identity digest), each
# re-measured whole; (4) if the fixed part with even the smallest notice still does not fit, OutputRefused is raised: a
# bounded refusal naming sizes only. Every returned page covers at least one position or is the empty end of a list, so a
# continuation always advances; nothing loops to build more work, and no identity is cut, renamed or aliased.
class OutputRefused(ValueError):
    """A navigation read whose smallest complete output cannot fit its line; the message names sizes, never identities."""


def line() -> int:
    """The line this owner call fits: the one the shared delivery plan gives a bounded native read (writing.delivery), or
    this owner's own page line CAP (its HTTP door adds nothing)."""
    from laplace.writing import delivery
    value = delivery.owner_line()
    return CAP if value is None else value


def emitted(value) -> int:
    """Bytes of the text both doors emit for this value (the shared writing.delivery measure)."""
    from laplace.writing import delivery
    return delivery.emitted(value)


def _oversized(project, ident, position, size, budget, *, inline=True):
    """The explicit notice for one position whose row cannot fit (repair2 WI-R5b): never cut, never renamed, never aliased.
    With ``inline`` false (its exact id would not fit either) it names only sizes and the identity digest."""
    raw = ident.encode('utf-8');fits = inline and len(raw) <= ID_INLINE_BYTES
    return {'position': position, 'row_bytes': size, 'page_line_bytes': budget, 'id_bytes': len(raw),
            'id_sha256': 'sha256:' + hashlib.sha256(raw).hexdigest(),
            **({'id': ident} if fits else {}),
            'says': ('This Work\'s navigation row alone exceeds the page line, so it is not shown here; '
                     + ('read it exactly with this page\'s row_reads.detail and its id.' if fits else
                        'its identity (%d bytes) cannot be carried within this page; the record is unchanged in the owner and only the '
                        'unbounded full read (view:full) delivers it.' % len(raw)))}


def _compose(ids, offset, limit, build, wrap, project, payload, cut, budget, *, part='page'):
    """The complete output of one navigation page that fits ``budget`` as emitted (see THE FINAL-OUTPUT INVARIANT).
    ``build(id)`` makes a row and ``wrap(rows, pagination)`` the whole output; positions are contiguous from offset."""
    from laplace.work import project_work_views as views
    from laplace.writing import delivery
    end = min(len(ids), offset + limit)

    def output(items):
        covered = len(items);nxt = offset + covered if offset + covered < len(ids) else None
        rows = [value for kind, value in items if kind == 'row'];notices = [value for kind, value in items if kind == 'oversized']
        page = {'total': len(ids), 'offset': offset, 'limit': limit, 'covered': covered, 'returned': len(rows), 'next_offset': nxt,
                'bounded_by': 'bytes' if covered < end - offset else 'limit',
                'next_read': views.handle(project, {**payload, 'offset': nxt, 'limit': limit, 'as_of': cut}) if nxt is not None else None}
        if notices:
            page.update(oversized=notices, complete=False,
                        coverage='%d of the %d positions covered here are not shown: each row alone exceeds the page line.' % (len(notices), covered))
        return wrap(rows, page)
    replay = (delivery.owner_replay() or {}).get(part)
    if replay is not None and replay.get('owner') == PROJECTION_OWNER:
        # a pure replay of a receipted page: exactly the positions and kinds it delivered, at its line; nothing measured,
        # so an unchanged owner reproduces the same bytes and a genuine change shows in the digest
        budget = replay['line'];items = []
        for position, kind in zip(range(offset, min(len(ids), offset + replay['covered'])), replay['kinds']):
            if kind == 'row':
                items.append(('row', build(ids[position])))
            else:
                items.append(('oversized', _oversized(project, ids[position], position, emitted(build(ids[position])) + 2, budget,
                                                      inline=kind == 'notice')))
        return output(items)
    items, estimate = [], 0
    for position in range(offset, end):   # (1) each position is tried once, in order
        row = build(ids[position]);cost = emitted(row) + 2
        if items:
            if estimate + cost > budget:
                break   # it does not fit after the rows already admitted: it starts the next page
            items.append(('row', row));estimate += cost
            continue
        # the first position: admitted as a row only if the complete one-row output fits, else as its notice
        first = [('row', row)] if emitted(output([('row', row)])) <= budget else \
            [('oversized', _oversized(project, ids[position], position, cost, budget))]
        items = first;estimate = emitted(output(items))
    value = output(items)
    while len(items) > 1 and emitted(value) > budget:   # (2) measured whole; drop the last item
        items.pop();value = output(items)
    if items and emitted(value) > budget:   # (3) one item left: demote it at most twice
        position = offset;ident = ids[position];size = emitted(build(ident)) + 2
        for inline in (True, False):
            items = [('oversized', _oversized(project, ident, position, size, budget, inline=inline))];value = output(items)
            if emitted(value) <= budget:
                break
    if emitted(value) > budget:   # (4) the fixed part leaves no room even for the smallest notice
        raise OutputRefused('This navigation page cannot be delivered within its %d-byte line: its fixed part (the opened Work, its '
                            'descriptor and reads) is %d bytes before any contained row. Read the Work with view:detail.'
                            % (budget, emitted(output([]))))
    delivery.record_projection(part, {'owner': PROJECTION_OWNER, 'line': budget, 'covered': len(items),
                                      'kinds': [kind if kind == 'row' else ('notice' if 'id' in item else 'digest') for kind, item in items]})
    return value


# ---------------------------------------------------------------------------------------------- descriptor

def action_context(index, ident, project, cut, allowed, *, full=True) -> dict:
    """The Work action/context descriptor of one Work at its grade (see the module text). Its actions name the entries of
    ``allowed`` (project_work_views._actions, the one carrier of handles, guards, statuses/refused, phase preparation,
    effects and recovery) and the guards each consumes; nothing about an action is decided or described twice."""
    from laplace.work import project_work_views as views, project_work_activity
    # full (the detail read): exact handles; coarse (a branch header): the page's row_reads with the target id, so a long
    # identity is not repeated by every read (repair3: the header is part of the measured page)
    read = (lambda view: views.handle(project, {'view': view, 'id': ident})) if full else (lambda view: {'row_reads': view, 'id': 'target.id'})
    row = index.by_id[ident];own = read('detail')
    grade = _grade(index, ident)
    deps = list(dict.fromkeys(row.get('depends_on') or []))
    open_deps = [dep for dep in deps if dep not in index.by_id or index.by_id[dep]['status'] not in {'done', 'verified'}]
    parent = row.get('parent_work_id')
    value = {'schema': 'laplace.work-action-context/2', 'grade': grade,
             'target': {'owner': 'project_work', 'project': project, 'id': ident, 'qualified_id': project + '::' + ident,
                        **{key: row.get(key) for key in ('work_revision', 'work_scope_revision', 'dependency_revision', 'work_status_revision')}},
             'basis': {'read_cut': cut, 'scope': 'Each action consumes only its own guards; an activity or observation change renews or stales none.'},
             'actions': [{'name': name, 'operation': action['operation'], 'permitted': action['permitted'],
                          'consumes': sorted(key for key in action['payload'] if key.startswith('expected_'))} for name, action in allowed.items()],
             'review_evidence_read':__import__('laplace.work.review_evidence',fromlist=['handle']).handle(project,ident),
             'carrier': {'field': 'allowed_actions', 'read': own,
                         'says': 'The exact handles, guards, admitted statuses and refusals, phase preparation, effects and recovery of these actions.'},
             'relationships': {
                 'parent': {'id': parent, 'title': index.by_id[parent].get('title') if parent in index.by_id else None,
                            'available': parent in index.by_id} if parent else None,
                 'contains': {'total': len(index.children.get(ident) or []), 'read': read('branch')},
                 'needs': {'total': len(deps), 'open': len(open_deps),
                           'says': 'Declared prerequisites: completion waits for each to be done on current acceptance.'},
                 'affects': {'total': len(index.dependants.get(ident) or []), 'says': 'Work that declares this as a prerequisite.'}},
             'qualifications': index.standing(ident)['facts'],
             'context': {'required': [{'read': own, 'answers': 'exact revisions, allowed actions, blockers and relationships'}],
                         'refine': 'Read only what the chosen action consumes; a missing or changed basis refuses with exact next reads.'}}
    if grade != 'task':
        rollup = index.rollup(ident)
        value['summary'] = {'descendants': rollup['descendants'], 'groups': rollup['groups'],
                            'next': rollup['next']['id'] if rollup['next'] else None, 'attention': rollup['attention_ids'][:6],
                            'preserves': ['qualified group counts over every contained Work', 'the first ready Work', 'the attention ids'],
                            'does_not_preserve': ['contained acceptance bases', 'evidence bytes', 'review findings'],
                            'descend': 'Read the contained Work (view:branch or view:detail) before acting on it; an action here acts on this Work only.'}
    if full:
        value['observation'] = project_work_activity.adapter()
    return value


# ---------------------------------------------------------------------------------------------- references and history

def _crumb(index, project, ident):
    return {'id': ident, 'qualified_id': project + '::' + ident, 'title': index.by_id[ident].get('title'), 'grade': _grade(index, ident)}


def _location(index, project, ident):
    trail, cyclic = index.ancestors(ident)
    return {'path': [_crumb(index, project, x) for x in trail[-BREADCRUMBS:]], 'omitted': max(0, len(trail) - BREADCRUMBS),
            'root': _crumb(index, project, trail[0]) if len(trail) > BREADCRUMBS else None, 'containment_cycle': cyclic}


def _history_rows(root, project, ident):
    rows = []
    for row in work._rows(root):
        if row.get('project') != project:
            continue
        record = row.get('record')
        if record in {'project-work', 'project-work-transition'} and (row.get('task_id') or row.get('id')) == ident:
            rows.append(row)
        elif record == 'project-work-phase' and row.get('work_id') == ident:
            rows.append(row)
    return rows


HISTORY_KEYS = ('title', 'goal', 'task_kind', 'parent_work_id', 'depends_on', 'section_ids', 'review_obligations', 'anchor', 'logical_target')


def _history_entries(rows):
    """Each recorded change of one Work, oldest first: specification (with the names it had and what changed), standing, phase."""
    out, prior = [], {}
    for row in rows:
        record = row.get('record')
        if record == 'project-work':
            changed = [key for key in HISTORY_KEYS if key in row and row.get(key) != prior.get(key)] if prior else ['created']
            out.append({'at': row.get('ts'), 'record': 'specification', 'title': row.get('title'), 'status': row.get('status'), 'changed': changed})
            prior = {**prior, **row}
        elif record == 'project-work-transition':
            out.append({'at': row.get('ts'), 'record': 'standing', 'status': row.get('status'),
                        **({'summary': _clip(row.get('summary'), PREVIEW_BYTES)[0]} if row.get('summary') else {})})
        elif row.get('kind')=='work-planning':
            plan=row.get('planning') or {}
            out.append({'at':row.get('ts'),'record':'planning','request_id':row.get('request_id'),'effect':row.get('effect'),
                        'planning':{k:plan[k] for k in ('priority','order','deferred') if k in plan},
                        'reason':_clip(plan.get('reason') or row.get('reason'),PREVIEW_BYTES)[0]})
        else:
            out.append({'at': row.get('ts'), 'record': 'review-phase', 'phase_id': row.get('id'), 'phase': row.get('phase'),
                        **{key: row[key] for key in ('state', 'verdict', 'obligation_id', 'child_id', 'finding', 'closure') if row.get(key)},
                        'evidence': len(row.get('evidence') or []), 'pins': len(row.get('pins') or {})})
    return out


def history_view(index, project, payload, root, cut, read_cut, offset, limit) -> dict:
    """THE RECORDED HISTORY of one Work (repair1 WI-R1 references): every specification row (its names and what changed),
    standing change and review phase, oldest first, paged under the read cut. Nothing is renamed or summarised away."""
    from laplace.work import project_work_views as views
    ident = payload.get('id')
    if ident not in index.by_id:
        raise ValueError('Exact work identity is unavailable in this namespace.')
    entries = _history_entries(_history_rows(root, project, ident))
    for entry in entries:
        if entry.get('record')=='planning':
            from laplace.work.backlog import request_read
            entry['read']=request_read(project,ident,entry['request_id'])
        if entry.get('phase_id'):
            from laplace.work.project_work_review import phase_read
            entry['read'] = phase_read(index.by_id[ident],root,entry['phase_id'],project=project)
    page = views._page(entries, offset, limit, project, payload, cut)
    return {'project': project, 'view': 'history', 'read_cut': read_cut, 'work': _crumb(index, project, ident),
            'entries': page.pop('items'), 'pagination': page,
            'scope': 'Recorded rows of this Work in ledger order; every historical name is kept. Phase bodies are their exact review reads.'}


def reference(index, ident, project, root) -> dict:
    """What a Work reference resolves to in its own project (repair1 WI-R1): exact qualified identity and title (codes in
    titles stay as authored; nothing is parsed from them), location (path, deeper omission and the root to descend from),
    recorded history counts with the history read, the recorded follow-up origin and follow-ups, and evidence counts. An
    unrecorded relation says so; no relation is inferred from a title or a code."""
    from laplace.work import project_work_views as views
    row = index.by_id[ident];rows = _history_rows(root, project, ident)
    counts = {'specification': sum(r.get('record') == 'project-work' for r in rows), 'standing': sum(r.get('record') == 'project-work-transition' for r in rows),
              'review_phases': sum(r.get('record') == 'project-work-phase' and r.get('kind') != 'work-planning' for r in rows),
              'planning': sum(r.get('record') == 'project-work-phase' and r.get('kind') == 'work-planning' for r in rows)}
    titles = list(dict.fromkeys(r.get('title') for r in rows if r.get('record') == 'project-work' and r.get('title')))
    value = {'review_evidence_read':__import__('laplace.work.review_evidence',fromlist=['handle']).handle(project,ident),'qualified_id': project + '::' + ident, 'title': row.get('title'), 'location': _location(index, project, ident),
             'history': {**counts, 'names': titles, 'read': views.handle(project, {'view': 'history', 'id': ident})}}
    origin = row.get('followup_origin')
    if origin:
        parent = origin.get('parent_work_id');phase = None
        for item in (index.by_id.get(parent) or {}).get('phases') or ():
            if item.get('phase') == 'followup' and item.get('child_id') == ident:
                phase = item.get('id')
        value['origin'] = {'recorded': True, 'relation': 'follow-up of a finding', 'finding': origin.get('finding'), 'closure': origin.get('closure'),
                           'parent': _crumb(index, project, parent) if parent in index.by_id else {'id': parent, 'available': False},
                           'record': __import__('laplace.work.project_work_review',fromlist=['phase_read']).phase_read(index.by_id[parent],root,phase,project=project) if phase and parent in index.by_id else None}
    else:
        value['origin'] = {'recorded': False, 'says': 'No recorded follow-up origin: this Work relates only through its declared containment and prerequisites.'}
    facet = row.get('review') or {}
    if facet.get('followups'):
        value['followups'] = [{'child': _crumb(index, project, item['child_id']) if item['child_id'] in index.by_id else {'id': item['child_id'], 'available': False},
                               'finding': item['finding'], 'closure': item['closure'], 'joined': item['joined'],
                               **({'standing': index.standing(item['child_id'])['group']} if item['child_id'] in index.by_id else {})}
                              for item in facet['followups']]
    value['evidence'] = {'completion': len(row.get('evidence') or []), 'review_phases_with_evidence': sum(bool(r.get('evidence')) for r in rows if r.get('record') == 'project-work-phase' and r.get('kind') != 'work-planning'),
                         'says': 'Completion evidence reads are in the detail; review-phase evidence and pins are the exact phase reads in the history.'}
    return value


# ---------------------------------------------------------------------------------------------- views

def _attention_row(index, ident, project):
    item = nav_row(index, ident, project)
    trail, _ = index.ancestors(ident)
    item['path'] = [{'id': x, 'title': _clip(index.by_id[x].get('title'), PREVIEW_BYTES)[0]} for x in trail[-3:]]
    if len(trail) > 3:
        item['path_omitted'] = len(trail) - 3
    return item


def roots_view(index, project, payload, cut, read_cut, offset, limit) -> dict:
    roots = index.roots()
    attention_ids = index.attention_ids()
    out = {'project': project, 'view': 'roots', 'read_cut': read_cut, 'observe_basis': index.observe_basis(),
           'counts': {'roots': len(roots), 'campaigns': sum(bool(index.children.get(ident)) for ident in roots),
                      'unfiled': sum(not index.children.get(ident) for ident in roots), 'work': len(index.by_id), 'attention': len(attention_ids),
                      'groups': index.group_counts()},
           'row_reads': row_reads(project),
           'scope': 'Root Work (no containing Work, or an unavailable/cyclic one) with complete subtree rollups; every Work is reachable from here.'}
    if offset == 0:
        out['attention'] = attention_page(index, project, cut, 0, ATTENTION_PREVIEW, budget=ATTENTION_BYTES)
    return _compose(roots, offset, limit, lambda ident: nav_row(index, ident, project),
                    lambda rows, page: {**out, 'roots': rows, 'pagination': page}, project, payload, cut, line())


def group_page(index, project, cut, group, offset, limit, *, payload, budget=None, wrap=None) -> dict:
    """One group's page: every Work whose qualified group is ``group`` at any depth (Index.group_ids), each the attention
    row (nav_row plus its containment path), composed under the read's line. ``payload`` is the read its continuation
    repeats; without ``wrap`` it is the roots attention preview (``budget`` its own share, pagination with items)."""
    return _compose(index.group_ids(group), offset, limit, lambda ident: _attention_row(index, ident, project),
                    wrap or (lambda rows, page: {**page, 'items': rows}), project, payload, cut, budget or line(),
                    part='attention-preview' if wrap is None else 'page')


def attention_page(index, project, cut, offset, limit, *, budget=None, wrap=None) -> dict:
    """An attention page: the roots preview (``budget`` its own share, pagination with items) or, with ``wrap``, the
    complete attention view held to the read's line."""
    return group_page(index, project, cut, 'attention', offset, limit, payload={'view': 'attention'}, budget=budget, wrap=wrap)


def branch_view(index, project, payload, cut, read_cut, offset, limit) -> dict:
    ident = payload.get('id')
    if ident not in index.by_id:
        raise ValueError('Exact work identity is unavailable in this namespace.')
    location = _location(index, project, ident)
    ordered, cyclic = index.sibling_order([x for x in index.children.get(ident) or [] if x in index.by_id])
    members = set(ordered)
    node = nav_row(index, ident, project)
    node['action_context'] = action_context(index, ident, project, cut, index.actions(ident), full=False)

    def child_row(child):
        item = nav_row(index, child, project);row = index.by_id[child]
        deps = list(dict.fromkeys(row.get('depends_on') or []))
        open_deps = [dep for dep in deps if dep not in index.by_id or index.by_id[dep]['status'] not in {'done', 'verified'}]
        item['needs'] = {'siblings': [dep for dep in deps if dep in members], 'outside': sum(dep not in members for dep in deps),
                         'open': len(open_deps), 'needed_by_siblings': sum(child in (index.by_id[x].get('depends_on') or []) for x in ordered)}
        if not open_deps and not (row.get('lifecycle') or {}).get('closed') and 'cycle' not in (row.get('blocked_by') or []):
            item['parallel'] = {'code': 'no-open-prerequisite'}
        return item
    out = {'project': project, 'view': 'branch', 'read_cut': read_cut, 'observe_basis': index.observe_basis(), 'node': node,
           'breadcrumbs': location['path'], 'breadcrumbs_omitted': location['omitted'], 'breadcrumbs_root': location['root'],
           **({'containment_cycle': True} if location['containment_cycle'] else {}),
           'order': {'kind': ('prerequisite-first; not deferred, higher priority, lower preferred order, stable legacy position' if any('planning' in index.by_id[x] for x in ordered) else 'authored order; a sibling prerequisite comes first'), 'cyclic': cyclic},
           'parallel_says': 'no-open-prerequisite: none of its declared prerequisites is open; conflicts, authority and resources are not assessed.',
           'row_reads': row_reads(project),
           'scope': 'One Work and its directly contained Work; relationships beyond the page are counted by the owner, not inferred.'}
    return _compose(ordered, offset, limit, child_row, lambda rows, page: {**out, 'children': rows, 'pagination': page},
                    project, payload, cut, line())


# ---------------------------------------------------------------------------------------------- observer token

def records_revision(raw) -> str:
    """The semantic Work records of a fold (specifications plus phase identities); never the ledger stat."""
    from laplace.work import project_work_views as views
    from laplace.work import project_work
    attached = project_work._ATTACHED_KEYS   # phases, development, deliveries: identities (id, state, ts), never bodies
    return views._hash({ident: {**{key: value for key, value in row.items() if key not in attached},
                                **{key: [(item.get('id'), item.get('state'), item.get('ts')) for item in row.get(key) or ()] for key in attached}}
                        for ident, row in raw.items()})


def _project_records(root, project, captured=None):
    """(fold, revision) from one captured owner project fold (``work._captured``); the revision is memoized against that
    fold object only while the owner retains its entry. An unretained (over-cap) ledger is computed from the same capture
    and leaves nothing here, so an empty result means the namespace actually has no Work records."""
    entry, fold = captured if captured is not None else work._captured(project, root)
    if not fold:
        return {}, 'sha256:' + '0' * 64
    key = (str(work._ledger(root)), project)
    if not work._retained(root, entry):
        with _TOKEN_LOCK:
            _TOKEN_CACHE.pop(key, None)
        return fold, records_revision(fold)
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(key)
        if cached is not None and cached[0] is fold:
            return fold, cached[1]
    revision = records_revision(fold)
    with _TOKEN_LOCK:
        _TOKEN_CACHE[key] = (fold, revision)
        while len(_TOKEN_CACHE) > 16:
            _TOKEN_CACHE.pop(next(iter(_TOKEN_CACHE)))
    return fold, revision


def observe(project, payload, root, *, now=None) -> dict:
    from laplace.work import project_work_views as views, project_work_activity
    captured = work._captured(project, root)   # one capture: records, selection and activity scopes share it
    fold, records = _project_records(root, project, captured)
    ident = payload.get('id')
    selected = records_revision({ident: fold[ident]}) if ident and ident in fold else ('absent' if ident else 'none')
    activity = project_work_activity.project_activity(project, root, now=now, captured=captured)
    parts = [records[7:19], (selected[7:19] if selected.startswith('sha256:') else selected), views._hash(activity['basis'])[7:19]]
    token = '.'.join([TOKEN_VERSION] + parts)
    since = payload.get('since');changes = None
    if since:
        prior = since.split('.')
        if len(prior) == 4 and prior[0] == TOKEN_VERSION:
            changes = [name for name, old, new in zip(('records', 'selected', 'activity'), prior[1:], parts) if old != new]
        else:
            changes = 'may-have-changed'
    selected_activity = activity['by_work'].get(ident) if ident else None
    if since and changes == []:
        # unchanged: the token alone (and the next expiry, which moves it without a write); the reads and the scope were
        # delivered with the baseline and are not repeated on every idle poll
        return {'project': project, 'view': 'observe', 'token': token, 'changed': False,
                **({'expires_next_at': activity['expires_next_at']} if activity['expires_next_at'] else {})}
    reads = {'catalogue': views.handle(project, {'view': 'roots'})}
    if ident and ident in fold:
        reads['selected'] = views.handle(project, {'view': 'detail', 'id': ident})
    return {'project': project, 'view': 'observe', 'token': token, 'since': since,
            'changed': None if since is None else bool(changes), 'changes': changes, 'reads': reads,
            'activity': {'selected': {key: selected_activity[key] for key in ('state', 'active', 'source', 'qualification')} if selected_activity else None,
                         'active_works': sum(item['active'] for item in activity['by_work'].values()),
                         'partial': activity['coverage']['partial']},
            'expires_next_at': activity['expires_next_at'], 'poll': POLL,
            'scope': 'A change hint: the named components may have changed. Not a guard or an evidence witness: re-read through '
                     'the named reads and compare each action\'s consumed basis before acting.'}
