"""Book hierarchy over stable projection-plan identities.

Storage remains a flat, ordered list for the existing plan ledger. Containment
is explicit; consumers receive preorder, ancestors and children, never infer
chapters from filenames or conflate them with conceptual prerequisites.
"""
from __future__ import annotations

KINDS = ('part', 'chapter', 'section', 'subsection', 'subsubsection')


def outline(rows: list[dict]) -> list[dict]:
    by_id = {row['id']: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError('Outline identities must be unique')
    children: dict[str | None, list[dict]] = {None: []}
    for row in rows:
        kind, parent = row.get('kind', 'section'), row.get('parent_id') or None
        if kind not in KINDS:
            raise ValueError('Unknown outline kind: ' + str(kind))
        if parent is not None:
            if parent not in by_id:
                raise ValueError('Outline parent is unavailable: ' + str(parent))
            if KINDS.index(by_id[parent].get('kind', 'section')) >= KINDS.index(kind):
                raise ValueError('Outline parent must be above its child (part, chapter, section, subsection)')
        children.setdefault(parent, []).append(row)
    result = []

    def visit(parent, ancestors, prefix):
        for index, row in enumerate(children.get(parent, []), 1):
            number = prefix + [index]
            result.append({**row, 'kind': row.get('kind', 'section'),
                           'parent_id': parent, 'depth': len(ancestors),
                           'number': '.'.join(map(str, number)),
                           'ancestor_ids': ancestors,
                           'child_ids': [r['id'] for r in children.get(row['id'], [])]})
            visit(row['id'], ancestors + [row['id']], number)
    visit(None, [], [])
    return result


def validate_plan(plan):
    # An appendix can have its own hierarchy, but cannot own a body chapter.
    outline(plan.get('sections') or [])
    outline(plan.get('appendices') or [])


def compact(row):
    return {key: row.get(key) for key in
            ('id', 'title', 'kind', 'parent_id', 'number', 'job', 'child_ids')}
