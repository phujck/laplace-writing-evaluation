"""Portable manuscript links and current Work inputs (WORK-editor-manuscript-evidence-link-export-20261015).

ONE qualified relationship, read where its owner keeps it, consumed by three places:

* the source manifest (``writing_eval_manifest.build``) inventories it: every owner link a selected
  manuscript carries (``\\href`` to the artifact or research-result human route, another app route or a
  canonical external URL, decoded by the walk's own TeX URL rule) admitted by the CANONICAL human owner
  (``research_artifact_read.resolve_read``: owner, receipt, scope, path and pin together; the Research
  catalogue for a result), and every input of the exact review the canonical Work facet selects, with
  that review's pins, verdict, currentness and independence and an honest disposition;
* the exporter projects it: with ``--work-inputs current`` an eligible current input outside the
  manuscript closure travels through the EXISTING pinned supplementary mechanism at its exact repository
  path; with ``--portable-document`` a derived copy of the selected source closure is staged under
  ``portable/<project>/`` whose links go to a readable appendix of qualified targets, with an HTML list
  and an exact record page for each linked result beside it, and a PDF through the declared build chain
  when it can run;
* the verifier checks, behind the shared admitted-read fence, that what the export declares about those
  relationships is what it holds.

Nothing here is a second link database or a second acceptance policy: the manuscript text, the artifact
owner, the Research catalogue and the Work review facet are the sources; this module reads them and
declares the projection in existing manifests. Historical records keep their original pins and statuses;
nothing is renewed, no empty stand-in is written, no history path is crawled. The author's source, built
PDF and history are never written.
"""
from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, quote, unquote, urlsplit

SCHEMA = 'laplace.portable-manuscript-links/1'
LINK_STATUSES = ('packaged', 'not-selected', 'changed', 'missing', 'unselected-project', 'refused', 'app-only', 'unavailable', 'external')
WORK_DISPOSITIONS = ('selected', 'supplementary', 'outside-closure', 'changed', 'missing', 'private')
APP_ROUTES = {'/research/artifact': 'artifact', '/research/result': 'research-result'}
_HEADING = re.compile(r'\\(chapter|section|subsection|subsubsection)\*?\{')
_PLAN = re.compile(r'^\s*%\s*PLAN:\s*(\S+)')
_TEX_ESCAPES = str.maketrans({'&': r'\&', '%': r'\%', '_': r'\_', '#': r'\#', '$': r'\$', '{': r'\{', '}': r'\}', '~': r'\~{}', '^': r'\^{}'})
_LOCAL_HOSTS = {'localhost', 'localhost.localdomain', '0.0.0.0', '::', 'ip6-localhost'}


def _sha(raw: bytes) -> str:
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------------------- the links in the TeX
def _braced(text: str, start: int):
    """The argument of the brace group opening at ``start`` (``text[start] == '{'``) and the index after it."""
    depth, i = 0, start
    while i < len(text):
        ch = text[i]
        if ch == '\\':
            i += 2
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    return None, len(text)


def tex_hrefs(text: str) -> list[dict]:
    """Every ``\\href{url}{label}`` of one TeX file: 1-based line, the owner URL decoded by the walk's literal rule
    (``walk._literal_tex_url``: a URL that still holds a macro is no URL), its exact source spelling, the label and
    the span of the whole macro, so a derived copy can replace it exactly."""
    from laplace.manuscript import walk
    out = []
    for match in re.finditer(r'\\href\{', text):
        url_source, after = _braced(text, match.end() - 1)
        if url_source is None or after >= len(text) or text[after] != '{':
            continue
        label, end = _braced(text, after)
        if label is None:
            continue
        line = text.count('\n', 0, match.start()) + 1
        out.append({'line': line, 'url': walk._literal_tex_url(url_source), 'url_source': url_source, 'label': label,
                    'start': match.start(), 'end': end})
    return out


def _local_host(host: str) -> bool:
    """A host this machine would answer for: a loopback or unspecified name, or a loopback/private/link-local address."""
    host = (host or '').strip('[]').lower()
    if not host:
        return True
    if host in _LOCAL_HOSTS or host.endswith('.local') or host.endswith('.localhost'):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local or address.is_unspecified


def _app_route(path: str, query: dict) -> dict:
    kind = APP_ROUTES.get(path)
    if kind == 'artifact':
        # the owner route's own coordinates, decoded ONCE by the query parser; a literal %2F in a file name stays a file name
        pin = str(query.get('expected_sha256') or '')
        match = re.fullmatch(r'(?:sha256:)?([a-fA-F0-9]{64})', pin)
        return {'kind': 'artifact', 'project': query.get('project'), 'scope': query.get('scope') or 'manuscript', 'path': query.get('path') or '',
                'expected_sha256': ('sha256:' + match[1].lower()) if match else None, 'artifact_id': query.get('artifact_id') or None,
                'owner': query.get('owner') or None}
    if kind == 'research-result':
        return {'kind': 'research-result', 'project': query.get('project'), 'id': query.get('id')}
    return {'kind': 'app-only', 'route': path, 'project': query.get('project')}


def human_link(url) -> dict:
    """What a link names, by a finite classification: an app route (relative, or absolute on a host this machine
    answers for: that is the same owner route, host-bound, never an external success), another path on such a
    host (``unavailable``: it works nowhere else), a canonical external URL on a public host (kept as written), or
    ``unknown`` (a provider working directory, a bare file path, an ART id, an unresolved macro)."""
    if not isinstance(url, str) or not url:
        return {'kind': 'unknown'}
    if url.startswith('/'):
        parts = urlsplit(url)
        query = {key: values[0] for key, values in parse_qs(parts.query, keep_blank_values=True).items()}
        return _app_route(parts.path, query)
    if re.match(r'^https?://', url):
        parts = urlsplit(url)
        if _local_host(parts.hostname or ''):
            query = {key: values[0] for key, values in parse_qs(parts.query, keep_blank_values=True).items()}
            if parts.path in APP_ROUTES:
                return {**_app_route(parts.path, query), 'host_bound': parts.netloc}
            return {'kind': 'unavailable', 'url': url, 'host': parts.netloc}
        return {'kind': 'external', 'url': url}
    return {'kind': 'unknown'}


def _context(lines: list[str], line: int) -> dict:
    """Where a link sits: the nearest heading above it (or the projector's PLAN section) and whether it is inside a
    figure or table environment. Read from the text; nothing is inferred beyond it."""
    heading, kind = None, 'paragraph'
    open_envs = []
    for index in range(line - 1, -1, -1):
        text = lines[index]
        for env in re.findall(r'\\end\{(figure\*?|table\*?)\}', text):
            open_envs.append(env)
        for env in re.findall(r'\\begin\{(figure\*?|table\*?)\}', text):
            if env in open_envs:
                open_envs.remove(env)
            elif kind == 'paragraph':
                kind = env.rstrip('*')
        if heading is None:
            match = _HEADING.search(text)
            if match:
                title, _end = _braced(text, match.end() - 1)
                heading = (title or '').strip()
            else:
                plan = _PLAN.match(text)
                if plan:
                    heading = plan.group(1)
    return {'heading': heading, 'kind': kind}


def _identity(link: dict) -> str:
    """One entry per admitted meaning: for an artifact the owner, receipt, scope, path and pin together (a refused
    owner or receipt is another relationship than the valid one at the same path)."""
    if link['kind'] == 'artifact':
        return 'artifact:%s:%s:%s:%s:%s:%s' % (link.get('project'), link.get('owner') or '', link.get('artifact_id') or '', link.get('scope'),
                                              link.get('path'), link.get('expected_sha256') or 'unpinned')
    if link['kind'] == 'research-result':
        return 'research-result:%s:%s' % (link.get('project'), link.get('id'))
    if link['kind'] in ('external', 'unavailable'):
        return link['kind'] + ':' + link['url']
    return link['kind'] + ':' + str(link.get('route') or '')


def _resolve_artifact(root: Path, link: dict, *, selected_projects, packaged) -> dict:
    """The CANONICAL human owner's admission (research_artifact_read.resolve_read): owner, receipt, scope, path and
    pin are judged together, exactly as the live link is; this projection only maps its answer onto the export."""
    from laplace.web import research_artifact_read
    project = link.get('project')
    if project not in selected_projects:
        return {'status': 'unselected-project', 'reason': 'the artifact belongs to project %r, which this export did not select; it is not copied' % project, 'target': None}
    if not link.get('expected_sha256'):
        return {'status': 'refused', 'reason': 'the link carries no complete byte identity (expected_sha256)', 'target': None}
    query = {'scope': link.get('scope') or '', 'path': link.get('path') or '', 'expected_sha256': link['expected_sha256'].removeprefix('sha256:')}
    if link.get('owner'):
        query['owner'] = link['owner']
    if link.get('artifact_id'):
        query['artifact_id'] = link['artifact_id']
    try:
        admitted = research_artifact_read.resolve_read(root, project, query)
    except (ValueError, OSError) as exc:
        return {'status': 'refused', 'reason': 'the artifact owner refused: ' + str(exc), 'target': None}
    if isinstance(admitted, tuple):
        try:
            detail = json.loads(admitted[2]).get('error')
        except (ValueError, TypeError, IndexError, AttributeError):
            detail = None
        return {'status': 'refused', 'reason': 'the artifact owner refused (%s): %s' % (admitted[0], detail or 'no exact target'), 'target': None}
    target = admitted.target
    if target is None:
        return {'status': 'refused', 'reason': 'the artifact owner resolved no exact target', 'target': None}
    resolved_root = root.resolve()
    if not target.is_relative_to(resolved_root):
        return {'status': 'refused', 'reason': 'the artifact resolves outside the checkout', 'target': None}
    rel = target.relative_to(resolved_root).as_posix()
    expected = 'sha256:' + admitted.expected if admitted.expected else link['expected_sha256']
    if not target.is_file():
        return {'status': 'missing', 'reason': 'the pinned artifact is absent at its owner coordinate %s' % rel, 'target': rel, 'current_sha256': None, 'admitted_sha256': expected}
    current = _sha(target.read_bytes())
    if current != expected:
        return {'status': 'changed', 'reason': 'the file at %s no longer has the pinned bytes; the link names the recorded revision, which is not substituted' % rel,
                'target': rel, 'current_sha256': current, 'admitted_sha256': expected}
    if rel not in packaged:
        return {'status': 'not-selected', 'reason': 'the pinned file exists but is not part of this export selection', 'target': rel, 'current_sha256': current, 'admitted_sha256': expected}
    return {'status': 'packaged', 'reason': None, 'target': rel, 'current_sha256': current, 'admitted_sha256': expected}


def _resolve_result(root: Path, link: dict, *, selected_projects, packaged, records_paths) -> dict:
    """The Research catalogue is the owner of a result's identity (research_catalogue.state_read view=result); the
    destination offered is the project's whole records file, labelled with the record id, until the portable copy
    generates the exact record page. No fragment that nothing answers is promised."""
    from laplace.research import research_catalogue
    project = link.get('project')
    if project not in selected_projects:
        return {'status': 'unselected-project', 'reason': 'the result belongs to project %r, which this export did not select' % project, 'target': None}
    status, payload = research_catalogue.state_read(project, root, view='result', ident=str(link.get('id') or ''))
    if status != 200:
        return {'status': 'missing', 'reason': 'the Research owner has no result %r for project %s (%s)' % (link.get('id'), project, payload.get('error') if isinstance(payload, dict) else status), 'target': None}
    rel = records_paths.get(project)
    if not rel or rel not in packaged:
        return {'status': 'not-selected', 'reason': 'the research records file that holds this result is not part of this export selection', 'target': rel, 'record': payload.get('result')}
    return {'status': 'packaged', 'reason': None, 'target': rel, 'record': payload.get('result'),
            'destination': 'the whole research records file, for inspection of record %s' % link.get('id')}


def manuscript_links(root: Path, project: str, files, *, selected_projects, packaged, records_paths=None) -> dict:
    """The owner links of one selected manuscript (``files``: repository-relative TeX closure files), each admitted
    once by its owner to ONE qualified target entry; repeated references with the same admitted meaning share the
    entry and list every place they occur."""
    root = Path(root).resolve()
    targets, order = {}, []
    references_total = 0
    for rel in files:
        if not rel.endswith('.tex'):
            continue
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        lines = text.split('\n')
        for found in tex_hrefs(text):
            link = human_link(found['url'])
            if link['kind'] == 'unknown':
                continue
            key = _identity(link)
            if key not in targets:
                if link['kind'] == 'artifact':
                    resolved = _resolve_artifact(root, link, selected_projects=selected_projects, packaged=packaged)
                elif link['kind'] == 'research-result':
                    resolved = _resolve_result(root, link, selected_projects=selected_projects, packaged=packaged, records_paths=records_paths or {})
                elif link['kind'] == 'external':
                    resolved = {'status': 'external', 'reason': 'a canonical URL on a public host; it is kept as written', 'target': None}
                elif link['kind'] == 'unavailable':
                    resolved = {'status': 'unavailable', 'reason': 'a URL bound to this machine (%s) that is not an owner route; it answers nowhere else and is not carried' % link.get('host'), 'target': None}
                else:
                    resolved = {'status': 'app-only', 'reason': 'an app route (%s); it opens in the Writing app and has no portable file target' % link.get('route'), 'target': None}
                entry = {'key': key, 'ordinal': len(order) + 1, 'label': found['label'], **link, **resolved, 'references': [], 'spellings': []}
                entry.pop('host_bound', None)
                targets[key] = entry
                order.append(key)
            references_total += 1
            # how the text spelled this one relationship: its owner route relative to the app, or bound to a host this
            # machine answers for (the same owner route; never an external success); recorded per reference and per entry
            spelling = ('host-bound:' + link['host_bound']) if link.get('host_bound') else 'app-route'
            if spelling not in targets[key]['spellings']:
                targets[key]['spellings'].append(spelling)
            targets[key]['references'].append({'file': rel, 'line': found['line'], 'label': found['label'], 'spelling': spelling, **_context(lines, found['line'])})
    rows = [targets[key] for key in order]
    return {'schema': SCHEMA, 'targets': rows, 'references_total': references_total,
            'by_status': {status: sum(1 for row in rows if row['status'] == status) for status in LINK_STATUSES if any(row['status'] == status for row in rows)},
            'qualification': 'owner links (\\href to an app route, relative or host-bound) in the selected TeX closure, decoded by the walk literal rule and '
                             'admitted by the canonical artifact owner (owner, receipt, scope, path, pin) or the Research catalogue; one entry per admitted '
                             'meaning; nothing is matched by basename or ART id'}


# ---------------------------------------------------------------------------------------- the Work inputs
def work_inputs(root: Path, project: str, *, packaged, supplementary=()) -> dict:
    """The inputs of every reviewed-or-declared Work obligation as the CANONICAL facet states them: for an obligation
    the facet resolved to an exact review, that review's own pins (its complete relevant recorded pins, which may
    cover inputs the obligation left undeclared) with the facet's verdict, currentness and independence; for an
    obligation without a review, its declared inputs, unreviewed (no pin is claimed for them). Each path gets an
    honest disposition for this export selection and an explicit eligibility for the current-input selection,
    which is the facet's own satisfaction (accepted, current, independent as required), never equal bytes."""
    from laplace.work import project_work, project_work_review
    from laplace.core import perimeter
    root = Path(root).resolve()
    tasks = project_work._tasks(project, root)
    supplementary = set(supplementary)
    rows = []
    for task in tasks.values():
        facet = project_work_review.facet(task, root, tasks=tasks, project=project)
        if not facet:
            continue
        declared = {item['id']: item for item in task.get('review_obligations') or [] if isinstance(item, dict) and item.get('id')}
        phases = {row.get('id'): row for row in task.get('phases') or () if isinstance(row, dict)}
        for entry in facet['obligations']:
            obligation = declared.get(entry['id']) or {}
            review = phases.get(entry.get('review_id')) if entry.get('review_id') else None
            pins = dict((review or {}).get('pins') or {})
            paths = list(dict.fromkeys([*pins, *(obligation.get('inputs') or [])]))
            selectable = bool(entry.get('satisfied')) and review is not None and bool(pins)
            if review is None:
                ineligible = 'no review recorded yet (%s)' % entry.get('status')
            elif not pins:
                ineligible = 'the review is coarse (no per-file pins)'
            elif not selectable:
                ineligible = '%s, %s%s' % (entry.get('status'), entry.get('currentness'),
                                           '' if not obligation.get('independent', True) or entry.get('independence') == 'INDEPENDENT' else ', not independent')
                if entry.get('currentness_reason'):
                    ineligible += ': ' + entry['currentness_reason']
            else:
                ineligible = None
            for path in paths:
                reviewed = path in pins
                pin = pins.get(path)
                try:
                    target = perimeter.public_repository_path(root, path)
                    private = None
                except ValueError as exc:
                    target, private = None, str(exc)
                current = _sha(target.read_bytes()) if target is not None and target.is_file() else None
                if private:
                    disposition, consequence = 'private', 'not a public repository path; it never travels and the imported review cannot be current'
                elif current is None:
                    disposition, consequence = 'missing', 'the input is absent now; a review of it is not current'
                elif reviewed and current != pin:
                    disposition, consequence = 'changed', 'the input changed since its review; the live review is STALE and stays so after import'
                elif path in packaged:
                    disposition, consequence = 'selected', ('travels with the project selection at its exact path' if reviewed else
                                                            'travels with the project selection at its exact path; it is declared, not yet reviewed, so no pin is claimed')
                elif path in supplementary:
                    disposition, consequence = 'supplementary', 'travels through an explicit pinned supplementary entry at its exact repository path'
                else:
                    disposition, consequence = 'outside-closure', ('a public file outside the selected manuscript closure that this export did not select; after import '
                                                                   + ('the review reads STALE until it is selected (--work-inputs current or a pinned supplementary entry)' if reviewed
                                                                      else 'a future review of it cannot be current until it is selected'))
                rows.append({'work_id': task['id'], 'obligation_id': entry['id'], 'label': entry.get('label'), 'required': bool(entry.get('required', True)),
                             'status': entry.get('status'), 'currentness': entry.get('currentness'), 'currentness_reason': entry.get('currentness_reason'),
                             'independence': entry.get('independence'), 'review_id': entry.get('review_id'), 'reviewed': reviewed,
                             'declared': path in (obligation.get('inputs') or []), 'path': path, 'review_pin': pin, 'current_sha256': current,
                             'disposition': disposition, 'consequence': consequence, 'selectable': selectable and reviewed and disposition == 'outside-closure',
                             'selection_reason': ineligible if not (selectable and reviewed) else None})
    return {'schema': 'laplace.portable-work-inputs/1', 'rows': rows,
            'by_disposition': {name: sum(1 for row in rows if row['disposition'] == name) for name in WORK_DISPOSITIONS if any(row['disposition'] == name for row in rows)},
            'qualification': 'the exact review each obligation resolves to in project_work_review.facet, with its own pins, verdict, currentness and independence; '
                             'declared inputs without a review are listed unreviewed with no pin claim; dispositions are for this export selection; no history '
                             'path is crawled, no pin is rewritten, no acceptance is derived from equal bytes'}


def admit_current_work_inputs(root: Path, inventory: dict) -> tuple[list[dict], list[dict]]:
    """What ``--work-inputs current`` selects and what it states it did not: an eligible outside-closure input (the
    facet's own satisfied review, its pin) becomes an explicit supplementary entry at its exact repository path; an
    outside-closure input the facet does not call current/accepted/independent, or an unreviewed one, is an
    explicit omission with the facet's reason; a reviewed input that is changed, missing or private refuses the
    selection before any copy, so the export never carries a renewed or empty stand-in."""
    root = Path(root).resolve()
    entries, omissions = [], []
    for row in inventory['rows']:
        if row['disposition'] in ('selected', 'supplementary'):
            continue
        if row['disposition'] != 'outside-closure':
            if row['reviewed']:
                raise ValueError('current Work input cannot travel: %s is %s (%s/%s); refresh the review or leave it honestly unselected'
                                 % (row['path'], row['disposition'], row['work_id'], row['obligation_id']))
            omissions.append({**{key: row[key] for key in ('work_id', 'obligation_id', 'path', 'disposition', 'status', 'currentness')},
                              'reason': 'declared but unreviewed input is %s; nothing is selected for it' % row['disposition'],
                              'live_observation': 'no review; obligation %s, %s' % (row.get('status'), row.get('currentness')), 'omitted_pin': None,
                              'consequence': 'the input stays outside the export; the imported canonical Work review facet alone decides the resulting status and currentness'})
            continue
        if row['selectable']:
            entries.append({'path': str(root / row['path']), 'repository_path': row['path'], 'sha256': row['review_pin'],
                            'reason': 'current Work review input of %s/%s (review %s: %s, %s, %s)' % (row['work_id'], row['obligation_id'], row['review_id'],
                                                                                                        row['status'], row['currentness'], row['independence'])})
        else:
            omissions.append({**{key: row[key] for key in ('work_id', 'obligation_id', 'path', 'disposition', 'status', 'currentness')},
                              'reason': 'not selected: ' + (row['selection_reason'] or 'the facet does not call this input current'),
                              'live_observation': 'review %s: %s, %s%s' % (row.get('review_id') or 'none', row.get('status'), row.get('currentness'),
                                                                        ('; ' + row['currentness_reason']) if row.get('currentness_reason') else ''),
                              'omitted_pin': row.get('review_pin'),
                              'consequence': ('the input stays outside the export; ' + ('its reviewed pin %s is then absent, which can make the imported review STALE; ' % row['review_pin'] if row.get('review_pin') else '')
                                              + 'the imported canonical Work review facet alone decides the resulting status and currentness')})
    return entries, omissions


def reconcile_omissions(omissions, final_inventory: dict) -> list[dict]:
    """Omissions are decided per Work relationship before any file travels; physical inclusion is per final path and
    pin, a union over every qualified selection (another obligation's accepted review, an explicit supplementary
    entry). This projects each omission against the FINAL inventory (the same work_inputs read over the export's
    actual packaged and supplementary paths): an input that travels after all is not physically omitted, so the
    omission says only that this obligation did not select it and records the carried disposition and whether the
    carried bytes are its reviewed pin; an input that is truly absent keeps its absence statement. The imported
    canonical facet still decides the resulting state; nothing here renews, selects or predicts."""
    final = {}
    for row in final_inventory.get('rows') or []:
        final.setdefault(row['path'], []).append(row)
    out = []
    for omission in omissions:
        rows = final.get(omission['path']) or []
        carried = [row for row in rows if row.get('disposition') in ('selected', 'supplementary')]
        if not carried:
            out.append({**omission, 'physically_carried': False})
            continue
        disposition = carried[0]['disposition']
        current = carried[0].get('current_sha256')
        pin = omission.get('omitted_pin')
        through = sorted({'%s/%s' % (row['work_id'], row['obligation_id']) for row in carried if (row['work_id'], row['obligation_id']) != (omission.get('work_id'), omission.get('obligation_id'))})
        out.append({**omission, 'physically_carried': True, 'carried_disposition': disposition, 'carried_sha256': current,
                    'pin_carried': bool(pin) and current == pin,
                    'carried_through': through or ['an explicit supplementary entry'],
                    'consequence': ('this obligation did not select the input, but the same path travels %s as %s%s; '
                                    'the imported canonical Work review facet alone decides the resulting status and currentness'
                                    % ('through ' + ', '.join(through) if through else 'through an explicit supplementary entry', disposition,
                                       (' at this review\'s pin' if pin and current == pin else (' at bytes other than this review\'s pin %s' % pin if pin else ''))))})
    return out


# ---------------------------------------------------------------------------------------- the portable document
def _tex(text: str) -> str:
    return str(text).translate(_TEX_ESCAPES)


def _tex_url(url: str) -> str:
    """The TeX carrier of an already-encoded URL: only TeX metacharacters are escaped (hyperref restores them)."""
    return url.replace('%', r'\%').replace('#', r'\#').replace('&', r'\&')


def _relative(frm: str, to: str) -> str:
    """The FILESYSTEM path of ``to`` relative to the directory of ``frm`` (both repository-relative, posix)."""
    return PurePosixPath(os.path.relpath(to, start=str(PurePosixPath(frm).parent) or '.')).as_posix()


def local_url(frm: str, to: str) -> str:
    """The relative URL that names the file ``to`` from the document ``frm``: the relative filesystem path with EACH
    segment percent-encoded exactly once (a literal %, #, ?, space or non-ASCII character in a file name is encoded;
    ``/`` separators and ``..`` are kept), so a URL consumer decoding it once reaches exactly that file. The HTML
    and TeX carriers escape this URL afterwards; filesystem, URL and carrier are three distinct steps."""
    return '/'.join(segment if segment in ('.', '..') else quote(segment, safe='') for segment in _relative(frm, to).split('/'))


def _anchor(ordinal: int) -> str:
    return 'portable-link-%d' % ordinal


def _status_words(row: dict) -> str:
    return {'packaged': 'packaged with this export', 'not-selected': 'exists in the source checkout but was not selected into this export',
            'changed': 'the recorded revision; the current file differs', 'missing': 'missing at its owner coordinate',
            'unselected-project': 'owned by a project this export did not select', 'refused': 'refused by the artifact owner',
            'app-only': 'opens in the Writing app only', 'unavailable': 'bound to the authoring machine; unavailable here', 'external': 'external URL'}.get(row['status'], row['status'])


def _record_page(project: str, row: dict) -> bytes:
    """The exact owner record of one linked research result, as its own small page: the destination a result link
    actually reaches (an element exists for it), not a fragment nothing answers."""
    esc = html.escape
    record = row.get('record')
    body = json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False)
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>Research result %s</title>'
            '<style>body{font:15px/1.5 system-ui;max-width:52em;margin:2em auto;padding:0 1em}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f6f6;padding:1em}</style></head><body>'
            '<h1 id="record">Research result <code>%s</code></h1><p>Project <code>%s</code>. The exact record as the Research owner holds it '
            '(research_catalogue.state_read view=result); the records file of the export is <code>%s</code>.</p><pre>%s</pre></body></html>\n'
            % (esc(str(row.get('id'))), esc(str(row.get('id'))), esc(str(project)), esc(str(row.get('records_file') or '')), esc(body))).encode('utf-8')


def _appendix_tex(project: str, links: dict, work: dict, omissions: list, appendix_rel: str) -> bytes:
    lines = ['%% Generated by scripts/writing_portable_links.py for the portable copy of project %s.' % project,
             '% Every entry is one qualified target the manuscript links to; the original manuscript keeps its app links.',
             r'\clearpage', r'\section*{Sources and artifacts}', r'\addcontentsline{toc}{section}{Sources and artifacts}',
             'Each link in this copy points here; each entry names its target, its status in this export and where the text uses it.', '']
    if not links['targets']:
        lines.append('This manuscript carries no owner links.')
    for row in links['targets']:
        # the destination stays OUT of the heading argument: a class may expand that argument (REVTeX's run-in
        # \paragraph* does, and \hypertarget is fragile there), so the anchor follows the heading on its own line,
        # where hyperref raises it to the heading; before the heading a page or column break could separate them
        lines.append(r'\paragraph*{%d.\ %s}\hypertarget{%s}{}%%' % (row['ordinal'], _tex(row['label']), _anchor(row['ordinal'])))
        kind = {'artifact': 'Artifact', 'research-result': 'Research result', 'external': 'External reference', 'unavailable': 'Machine-bound URL', 'app-only': 'App route'}.get(row['kind'], row['kind'])
        detail = []
        if row['kind'] == 'artifact':
            detail.append('%s \\texttt{%s} (%s scope, project %s%s)' % (kind, _tex(row.get('path') or ''), _tex(row.get('scope') or ''), _tex(row.get('project') or ''),
                                                                          (', receipt ' + _tex(row['artifact_id'])) if row.get('artifact_id') else ''))
            if row.get('expected_sha256'):
                detail.append('recorded revision \\texttt{%s}' % _tex(row['expected_sha256'][:23]))
        elif row['kind'] == 'research-result':
            detail.append('%s \\texttt{%s} (project %s)' % (kind, _tex(row.get('id') or ''), _tex(row.get('project') or '')))
        elif row['kind'] == 'external':
            detail.append('%s \\url{%s}' % (kind, _tex_url(row['url'])))
        elif row['kind'] == 'unavailable':
            # readable, breakable spelling with NO link action: hyperref's \nolinkurl typesets a URL without a URI annotation
            detail.append('%s \\nolinkurl{%s} (not linked: it answers only on %s)' % (kind, _tex_url(row['url']), _tex(row.get('host') or 'the authoring machine')))
        else:
            detail.append('%s \\texttt{%s}' % (kind, _tex(row.get('route') or '')))
        lines.append('; '.join(detail) + '.')
        status = _status_words(row)
        if row['status'] == 'packaged' and row.get('target'):
            target = local_url(appendix_rel, row['target'])
            lines.append('Status: %s: \\href{%s}{\\texttt{%s}}%s.' % (status, _tex_url(target), _tex(row['target']),
                         (' (' + _tex(row['destination']) + ')') if row.get('destination') else ''))
        else:
            lines.append('Status: %s.%s' % (status, ' ' + _tex(row['reason']) if row.get('reason') else ''))
        places = ['%s (%s:%d%s)' % (_tex(ref['heading'] or 'untitled'), _tex(ref['file']), ref['line'], ', ' + ref['kind'] if ref['kind'] != 'paragraph' else '')
                  for ref in row['references']]
        lines.append('Used in: ' + '; '.join(places) + '.')
        lines.append('')
    rows = work.get('rows') or []
    if rows or omissions:
        lines += [r'\subsection*{Reviewed Work inputs}', 'Inputs of reviewed Work obligations as the Work review owner states them, and whether they travel with this export.', r'\begin{itemize}']
        for row in rows:
            lines.append(r'\item \texttt{%s}: %s/%s (%s, %s%s), %s. %s' % (_tex(row['path']), _tex(row['work_id']), _tex(row['obligation_id']), _tex(row['status'] or ''), _tex(row['currentness'] or ''),
                                                                         '' if row['reviewed'] else ', unreviewed', _tex(row['disposition']), _tex(row['consequence'])))
        for row in omissions:
            lines.append(r'\item Not selected: \texttt{%s} of %s/%s: %s%s' % (_tex(row['path']), _tex(row['work_id']), _tex(row['obligation_id']), _tex(row['reason']),
                                                                             (' ' + _tex(row['consequence']) + '.') if row.get('consequence') else ''))
        lines.append(r'\end{itemize}')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def _html_list(project: str, links: dict, work: dict, omissions: list, html_rel: str, pdf_rel: str | None, derived_root: str, source_root: str) -> bytes:
    esc = html.escape
    parts = ['<!doctype html>', '<html lang="en"><head><meta charset="utf-8"><title>Sources and artifacts: %s</title>' % esc(project),
             '<style>body{font:15px/1.5 system-ui;max-width:52em;margin:2em auto;padding:0 1em}dt{font-weight:600;margin-top:1em}dd{margin:0 0 .4em 1em}code{font-size:.92em}.status{color:#444}</style></head><body>',
             '<h1>Sources and artifacts</h1>', '<p>The links of the manuscript <code>%s</code> in this export, each admitted once by its owner. ' % esc(source_root)
             + 'The portable copy <code>%s</code>%s sends every link to the matching entry below; the original manuscript keeps its app links.</p>'
             % (esc(derived_root), (' and its PDF <a href="%s">%s</a>' % (esc(local_url(html_rel, pdf_rel)), esc(PurePosixPath(pdf_rel).name))) if pdf_rel else ' (no PDF was built; see the export manifest)'),
             '<dl>']
    for row in links['targets']:
        parts.append('<dt id="%s">%d. %s</dt>' % (esc(_anchor(row['ordinal'])), row['ordinal'], esc(row['label'])))
        if row['kind'] == 'artifact':
            parts.append('<dd>Artifact <code>%s</code> (%s scope, project %s%s)%s</dd>' % (esc(row.get('path') or ''), esc(row.get('scope') or ''), esc(row.get('project') or ''),
                         (', receipt <code>%s</code>' % esc(row['artifact_id'])) if row.get('artifact_id') else '',
                         (', recorded revision <code>%s</code>' % esc(row['expected_sha256'][:23])) if row.get('expected_sha256') else ''))
        elif row['kind'] == 'research-result':
            parts.append('<dd>Research result <code>%s</code> (project %s)</dd>' % (esc(row.get('id') or ''), esc(row.get('project') or '')))
        elif row['kind'] == 'external':
            parts.append('<dd>External reference <a href="%s" rel="external">%s</a></dd>' % (esc(row['url']), esc(row['url'])))
        elif row['kind'] == 'unavailable':
            parts.append('<dd>Machine-bound URL <code>%s</code> (not linked: it answers only on %s)</dd>' % (esc(row['url']), esc(row.get('host') or 'the authoring machine')))
        else:
            parts.append('<dd>App route <code>%s</code></dd>' % esc(row.get('route') or ''))
        if row['status'] == 'packaged' and row.get('target'):
            parts.append('<dd class="status">Status: %s: <a href="%s"><code>%s</code></a>%s</dd>' % (esc(_status_words(row)), esc(local_url(html_rel, row['target'])), esc(row['target']),
                         (' (' + esc(row['destination']) + ')') if row.get('destination') else ''))
        else:
            parts.append('<dd class="status">Status: %s.%s</dd>' % (esc(_status_words(row)), (' ' + esc(row['reason'])) if row.get('reason') else ''))
        parts.append('<dd>Used in: %s</dd>' % '; '.join('%s (<code>%s:%d</code>%s)' % (esc(ref['heading'] or 'untitled'), esc(ref['file']), ref['line'], ', ' + esc(ref['kind']) if ref['kind'] != 'paragraph' else '')
                                                        for ref in row['references']))
    parts.append('</dl>')
    rows = work.get('rows') or []
    if rows or omissions:
        parts.append('<h2>Reviewed Work inputs</h2><ul>')
        for row in rows:
            parts.append('<li><code>%s</code>: %s/%s (%s, %s%s), <strong>%s</strong>. %s</li>' % (esc(row['path']), esc(row['work_id']), esc(row['obligation_id']), esc(row['status'] or ''),
                         esc(row['currentness'] or ''), '' if row['reviewed'] else ', unreviewed', esc(row['disposition']), esc(row['consequence'])))
        for row in omissions:
            parts.append('<li>Not selected: <code>%s</code> of %s/%s: %s%s</li>' % (esc(row['path']), esc(row['work_id']), esc(row['obligation_id']), esc(row['reason']),
                                                                                   (' ' + esc(row['consequence']) + '.') if row.get('consequence') else ''))
        parts.append('</ul>')
    parts.append('</body></html>')
    return ('\n'.join(parts) + '\n').encode('utf-8')


def portable_document(root: Path, project: str, *, source_root: str, closure_files, links: dict, work: dict, omissions=()) -> dict:
    """The derived portable copy of one selected source closure: every closure file under ``portable/<project>/``
    in its original relative layout, each ``\\href`` to an owner link replaced by a link to the appendix entry, the
    appendix input before ``\\end{document}``, an exact record page for each packaged result (which becomes that
    result's destination), and the HTML list. Returns ``{'files': {path: bytes}, 'mapping': {...}}``; nothing is
    written here and the author's files are only read."""
    root = Path(root).resolve()
    prefix = PurePosixPath('portable') / project
    derived_root = (prefix / source_root).as_posix()
    files, mapping_files = {}, []
    anchors = {row['key']: row['ordinal'] for row in links['targets']}
    pages = {}
    for row in links['targets']:
        if row['kind'] == 'research-result' and row['status'] == 'packaged' and row.get('record') is not None:
            # the page name is a digest of the qualified identity (project and the owner's exact result id), so any
            # two distinct valid ids get distinct pages; the id itself is not narrowed, and a collision is refused
            page_rel = (prefix / 'records' / (hashlib.sha256(row['key'].encode('utf-8')).hexdigest()[:32] + '.html')).as_posix()
            if pages.get(page_rel, row['key']) != row['key'] or page_rel in files:
                raise ValueError('record page name collision between %r and %r' % (pages.get(page_rel), row['key']))
            pages[page_rel] = row['key']
            row['records_file'] = row['target']
            files[page_rel] = _record_page(project, row)
            mapping_files.append({'derived': page_rel, 'source': None, 'derivation': 'exact owner record projection of research result %s (research_catalogue.state_read view=result)' % row['id']})
            row['target'] = page_rel
            row['destination'] = 'exact record page generated from the Research owner'
    for rel in closure_files:
        path = root / rel
        if not path.is_file():
            continue
        raw = path.read_bytes()
        derived_rel = (prefix / rel).as_posix()
        if rel.endswith('.tex'):
            text = raw.decode('utf-8', errors='replace')
            pieces, cursor = [], 0
            for found in tex_hrefs(text):
                link = human_link(found['url'])
                if link['kind'] == 'unknown':
                    continue
                ordinal = anchors.get(_identity(link))
                if ordinal is None:
                    continue
                pieces.append(text[cursor:found['start']])
                # \protect: an owner link may sit in a moving argument (a figure caption), where \hyperlink alone breaks
                pieces.append(r'\protect\hyperlink{%s}{%s}' % (_anchor(ordinal), found['label']))
                cursor = found['end']
            pieces.append(text[cursor:])
            text = ''.join(pieces)
            if rel == source_root:
                appendix_rel = (PurePosixPath(derived_root).parent / 'portable-links.tex').as_posix()
                files[appendix_rel] = _appendix_tex(project, links, work, list(omissions), appendix_rel)
                mapping_files.append({'derived': appendix_rel, 'source': None, 'derivation': 'generated appendix of qualified link targets and reviewed Work inputs'})
                end = text.rfind(r'\end{document}')
                insertion = '\\input{portable-links}\n'
                text = (text[:end] + insertion + text[end:]) if end >= 0 else text + '\n' + insertion
            raw = text.encode('utf-8')
        files[derived_rel] = raw
        mapping_files.append({'derived': derived_rel, 'source': rel, 'source_sha256': _sha(path.read_bytes()),
                              'derivation': 'owner links replaced by appendix links; appendix input added before \\end{document}' if rel == source_root
                              else ('owner links replaced by appendix links' if rel.endswith('.tex') else 'exact copy for compilation')})
    html_rel = (prefix / 'links.html').as_posix()
    mapping = {'schema': 'laplace.portable-document/1', 'project': project, 'source_root': source_root, 'derived_root': derived_root,
               'appendix': (PurePosixPath(derived_root).parent / 'portable-links.tex').as_posix(), 'html': html_rel, 'pdf': None, 'compiler': None,
               'files': mapping_files, 'links': {'targets': len(links['targets']), 'references': links['references_total'], 'by_status': links['by_status']},
               'work_inputs': work.get('by_disposition') or {}, 'work_input_omissions': list(omissions),
               'qualification': 'a derived copy for portable reading; the original manuscript, its built PDF and its history are unchanged and keep their '
                                'live app links; a target that is not packaged is stated as such in the appendix and never substituted'}
    return {'files': files, 'mapping': mapping, 'html_rel': html_rel}


def compile_portable(files: dict, derived_root: str, *, timeout: int = 240) -> dict:
    """Compile the derived copy through the declared build chain (projection_viewer: latexmk -pdf, else the pdflatex
    sequence) in a scratch directory that holds only the derived files. Returns the PDF bytes or the exact reason
    there are none; no placeholder is ever produced."""
    import time
    from laplace.manuscript import projection_viewer
    with tempfile.TemporaryDirectory(prefix='laplace-portable-build-') as scratch:
        base = Path(scratch)
        for rel, raw in files.items():
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        tex = base / derived_root
        cwd = tex.parent
        started = time.time()
        latexmk = projection_viewer._latexmk_bin()
        chain = []
        if latexmk:
            ok, out = projection_viewer._run([latexmk, '-pdf', '-interaction=nonstopmode', '-halt-on-error', tex.name], cwd, timeout)
            chain.append({'tool': 'latexmk', 'binary': latexmk, 'ok': bool(ok)})
            if not ok:
                ok, out = projection_viewer._pdflatex_sequence(tex, cwd)
                chain.append({'tool': 'pdflatex-sequence', 'binary': projection_viewer._pdflatex_bin(), 'ok': bool(ok)})
        elif projection_viewer._pdflatex_bin():
            ok, out = projection_viewer._pdflatex_sequence(tex, cwd)
            chain.append({'tool': 'pdflatex-sequence', 'binary': projection_viewer._pdflatex_bin(), 'ok': bool(ok)})
        else:
            return {'ok': False, 'pdf': None, 'missing_capability': 'neither latexmk nor pdflatex is installed (projection_viewer._latexmk_bin/_pdflatex_bin)', 'chain': chain, 'log_tail': ''}
        pdf = tex.with_suffix('.pdf')
        log = str(out)
        tail = '\n'.join(log.splitlines()[-40:])
        # the chain's own law (projection_viewer.compile_tex): success is a FRESH PDF, not an exit code; and a PDF that
        # TeX wrote past errors (nonstopmode) is not a clean build, so the error lines are the verdict and travel with it
        errors = [line for line in log.splitlines() if line.startswith('! ')][:12]
        fresh = pdf.is_file() and pdf.stat().st_size > 0 and pdf.stat().st_mtime >= started - 1.0
        if not fresh or errors:
            return {'ok': False, 'pdf': None, 'missing_capability': None, 'chain': chain, 'log_tail': tail, 'errors': errors,
                    'reason': 'TeX reported errors while building the derived copy' if errors else 'the build chain did not produce the PDF'}
        return {'ok': True, 'pdf': pdf.read_bytes(), 'chain': chain, 'log_tail': tail, 'errors': []}


# ---------------------------------------------------------------------------------------- the compiled PDF's URI actions
URI_PASS = ('compiled-PDF URI actions read from qpdf --json-output (JSON v2, stream data inline and undecoded) and written back from that '
            'same document with qpdf --json-input --deterministic-id')


def _pdf_text(value):
    """A qpdf JSON v2 string value as text (``u:`` UTF-8, ``b:`` hex bytes, read as Latin-1), else None."""
    if isinstance(value, str) and value.startswith('u:'):
        return value[2:]
    if isinstance(value, str) and value.startswith('b:'):
        try:
            return bytes.fromhex(value[2:]).decode('latin-1')
        except ValueError:
            return None
    return None


def uri_disposition(uri: str, *, derived_pdf: str, original_pdf: str, admitted: dict, present) -> dict:
    """What one URI action of the derived PDF becomes. Finite: ``external`` (a public URL, kept), ``same-document``
    (a fragment or query alone, kept), ``portable`` (a relative reference that already reaches a file of this export
    from the derived PDF, kept), ``rebased`` (a relative reference whose meaning beside the ORIGINAL PDF is a selected
    file at its pin: the same target, named from the derived PDF), or ``unavailable`` (bound to the authoring machine,
    an absolute path, outside the export or a file this export does not carry: the link action is removed and the
    printed text stays). Identity is decided only against ``admitted`` (path -> pin) and ``present``; nothing is read."""
    parts = urlsplit(uri)
    scheme = parts.scheme.lower()
    if scheme == 'file' or (scheme in ('http', 'https', '') and parts.netloc and _local_host(parts.hostname or '')):
        return {'disposition': 'unavailable', 'reason': 'bound to the authoring machine (%s); it answers nowhere else' % (parts.netloc or 'file')}
    if scheme or parts.netloc:
        return {'disposition': 'external'}
    if not parts.path:
        return {'disposition': 'same-document'}
    if parts.path.startswith('/'):
        return {'disposition': 'unavailable', 'reason': 'an absolute path or app route; only the authoring machine or the Writing app answers it'}
    spelling = unquote(parts.path)
    here = posixpath.normpath(posixpath.join(posixpath.dirname(derived_pdf), spelling))
    if here in present:
        return {'disposition': 'portable', 'target': here}
    there = posixpath.normpath(posixpath.join(posixpath.dirname(original_pdf), spelling))
    if there == '..' or there.startswith('../') or there.startswith('/'):
        return {'disposition': 'unavailable', 'reason': 'its meaning beside the original PDF lies outside the export'}
    if there not in admitted:
        return {'disposition': 'unavailable', 'reason': 'its meaning beside the original PDF is %s, which this export does not carry' % there}
    rebased = local_url(derived_pdf, there) + ('?' + parts.query if parts.query else '') + ('#' + parts.fragment if parts.fragment else '')
    return {'disposition': 'rebased', 'target': there, 'sha256': admitted[there], 'to': rebased}


def relocate_uri_actions(pdf: bytes, *, derived_pdf: str, original_pdf: str, admitted: dict, present, timeout: int = 120) -> dict:
    """The derived PDF's URI link actions made true at its new location (uri_disposition per action): rebased actions
    name the same selected file from the derived PDF, unavailable ones lose their link annotation, everything else
    (external URLs, GoTo destinations, text, pages) is untouched. A PDF needing no change keeps its exact bytes. The
    result is re-read and every remaining URI action must be kept-class, else the pass refuses. Returns ``{'ok',
    'pdf', 'record'}``; a missing qpdf or an unreadable PDF is a finite refusal, never an unprocessed PDF."""
    qpdf = shutil.which('qpdf')
    if not qpdf:
        return {'ok': False, 'pdf': None, 'record': {'pass': URI_PASS, 'missing_capability': 'qpdf is not installed; the PDF URI actions cannot be checked or relocated'}}
    decide = lambda uri: uri_disposition(uri, derived_pdf=derived_pdf, original_pdf=original_pdf, admitted=admitted, present=present)

    def read(path):
        # the whole document in qpdf's lossless JSON v2 form; streams stay as their exact filtered bytes (decode level none)
        run = subprocess.run([qpdf, str(path), '--json-output', '--json-stream-data=inline', '--decode-level=none', '-'], capture_output=True, timeout=timeout)
        if run.returncode not in (0, 3):
            return None, None
        document = json.loads(run.stdout)
        return document, document['qpdf'][1]

    def actions(objects):
        found, inline = [], 0
        for key, entry in objects.items():
            value = entry.get('value') if isinstance(entry, dict) else None
            if isinstance(value, dict) and value.get('/Type') == '/Page' and isinstance(value.get('/Annots'), list):
                inline += sum(1 for item in value['/Annots'] if isinstance(item, dict))
            if not (isinstance(value, dict) and value.get('/Subtype') == '/Link'):
                continue
            action, holder = value.get('/A'), None
            if isinstance(action, str) and action.endswith(' R'):
                holder = 'obj:' + action
                action = (objects.get(holder) or {}).get('value')
            if isinstance(action, dict) and action.get('/S') == '/URI':
                found.append({'annotation': key, 'holder': holder, 'uri': _pdf_text(action.get('/URI'))})
        return found, inline

    with tempfile.TemporaryDirectory(prefix='laplace-portable-uri-') as scratch:
        base = Path(scratch)
        compiled = base / 'compiled.pdf'
        compiled.write_bytes(pdf)
        document, objects = read(compiled)
        if objects is None:
            return {'ok': False, 'pdf': None, 'record': {'pass': URI_PASS, 'reason': 'qpdf could not read the compiled PDF'}}
        found, inline = actions(objects)
        if inline:
            return {'ok': False, 'pdf': None, 'record': {'pass': URI_PASS, 'reason': 'the PDF carries %d inline page annotations; only indirect link annotations are handled' % inline}}
        dropped, rebased, unavailable, kept = set(), [], [], {}
        for row in found:
            decision = decide(row['uri']) if row['uri'] is not None else {'disposition': 'unavailable', 'reason': 'the URI is not a PDF string'}
            if decision['disposition'] == 'rebased':
                key = row['holder'] or row['annotation']
                target = objects[key]['value'] if row['holder'] else objects[key]['value']['/A']
                target['/URI'] = 'u:' + decision['to']
                rebased.append({'uri': row['uri'], 'to': decision['to'], 'target': decision['target'], 'sha256': decision['sha256']})
            elif decision['disposition'] == 'unavailable':
                dropped.add(row['annotation'][len('obj:'):])
                unavailable.append({'uri': row['uri'], 'reason': decision['reason']})
            else:
                kept[decision['disposition']] = kept.get(decision['disposition'], 0) + 1
        record = {'pass': URI_PASS, 'compiled_sha256': _sha(pdf), 'uri_actions': len(found), 'kept': kept,
                  'rebased': rebased, 'unavailable': unavailable, 'unchanged': not (rebased or unavailable)}
        if not (rebased or unavailable):
            return {'ok': True, 'pdf': pdf, 'record': record}
        for key, entry in list(objects.items()):   # drop the unavailable annotations from every /Annots array that lists them
            value = entry.get('value') if isinstance(entry, dict) else None
            if isinstance(value, dict) and value.get('/Type') == '/Page' and isinstance(value.get('/Annots'), list):
                value['/Annots'] = [item for item in value['/Annots'] if item not in dropped]
            elif isinstance(value, dict) and value.get('/Type') == '/Page' and isinstance(value.get('/Annots'), str):
                listed = (objects.get('obj:' + value['/Annots']) or {}).get('value')
                if isinstance(listed, list):
                    objects['obj:' + value['/Annots']]['value'] = [item for item in listed if item not in dropped]
        edited = base / 'relocated.json'
        edited.write_text(json.dumps(document))
        out = base / 'relocated.pdf'
        run = subprocess.run([qpdf, '--json-input', str(edited), '--deterministic-id', str(out)], capture_output=True, timeout=timeout)
        if run.returncode not in (0, 3) or not out.is_file():
            return {'ok': False, 'pdf': None, 'record': {**record, 'reason': 'qpdf could not write the relocated PDF: ' + run.stderr.decode('utf-8', 'replace')[:300]}}
        _document, final = read(out)
        remaining = actions(final)[0] if final is not None else None
        wrong = [row['uri'] for row in (remaining or []) if row['uri'] is None or decide(row['uri'])['disposition'] in ('rebased', 'unavailable')]
        if remaining is None or wrong or len(remaining) != len(found) - len(unavailable):
            return {'ok': False, 'pdf': None, 'record': {**record, 'reason': 'the relocated PDF still carries URI actions that are not portable: %s' % (wrong or 'unreadable')[:5]}}
        return {'ok': True, 'pdf': out.read_bytes(), 'record': record}


# ---------------------------------------------------------------------------------------- the verifier's part
def _is_str(value) -> bool:
    return isinstance(value, str) and bool(value)


def _opt_str(value) -> bool:
    return value is None or isinstance(value, str)


def portable_shape_problems(report: dict) -> list[str]:
    """Why the export manifest's optional portable metadata is not a supported shape; empty when it is (or absent).
    One admission of every container and field the verifier will touch, in the style of
    writing_export_bytes.manifest_shape_problems; nothing is read from the export here."""
    problems = []
    docs = report.get('portable_documents')
    if docs is not None:
        if not isinstance(docs, dict):
            problems.append('portable_documents is not an object keyed by project')
        else:
            for project, doc in docs.items():
                where = 'portable_documents[%r]' % (project,)
                if not isinstance(doc, dict):
                    problems.append(where + ' is not an object'); continue
                files = doc.get('files')
                if not isinstance(files, list) or any(not (isinstance(row, dict) and _is_str(row.get('derived')) and _opt_str(row.get('source')) and _opt_str(row.get('source_sha256'))) for row in files):
                    problems.append(where + '.files is not a list of {derived: string, source: string|null, source_sha256: string|null}')
                for key in ('html', 'appendix', 'derived_root'):
                    if not _opt_str(doc.get(key)):
                        problems.append(where + '.' + key + ' is not a string or null')
                pdf = doc.get('pdf')
                if pdf is not None and not (isinstance(pdf, dict) and _is_str(pdf.get('path')) and _is_str(pdf.get('sha256'))):
                    problems.append(where + '.pdf is not null or {path: string, sha256: string}')
                compiler = doc.get('compiler')
                if compiler is not None and not isinstance(compiler, dict):
                    problems.append(where + '.compiler is not null or an object')
    links = report.get('manuscript_links')
    if links is not None:
        if not isinstance(links, dict):
            problems.append('manuscript_links is not an object keyed by project')
        else:
            for project, value in links.items():
                where = 'manuscript_links[%r]' % (project,)
                rows = value.get('targets') if isinstance(value, dict) else None
                if not isinstance(rows, list):
                    problems.append(where + '.targets is not a list'); continue
                bad = sum(1 for row in rows if not (isinstance(row, dict) and _is_str(row.get('status')) and _is_str(row.get('kind')) and _opt_str(row.get('key')) and _opt_str(row.get('target'))
                                                    and _opt_str(row.get('reason')) and _opt_str(row.get('admitted_sha256')) and _opt_str(row.get('expected_sha256'))))
                if bad:
                    problems.append(where + '.targets has %d rows without string status and kind and string-or-null key, target, reason and pins' % bad)
    work = report.get('work_inputs')
    if work is not None:
        if not isinstance(work, dict):
            problems.append('work_inputs is not an object keyed by project')
        else:
            for project, value in work.items():
                where = 'work_inputs[%r]' % (project,)
                rows = value.get('rows') if isinstance(value, dict) else None
                if not isinstance(rows, list):
                    problems.append(where + '.rows is not a list'); continue
                bad = sum(1 for row in rows if not (isinstance(row, dict) and _is_str(row.get('path')) and _is_str(row.get('disposition')) and isinstance(row.get('reviewed', False), bool)
                                                    and _opt_str(row.get('review_pin'))))
                if bad:
                    problems.append(where + '.rows has %d rows without a string path and disposition, a boolean reviewed and a string-or-null review_pin' % bad)
    return problems


def verify_portable(report: dict, pins: dict, *, admit, identity) -> tuple[list[dict], dict]:
    """What the export declares about links and Work inputs is what it holds, read ONLY through the shared admitted
    read contract: ``admit(relative)`` is the verifier's Fence (regular file inside the root, no symlink component,
    no climb) and ``identity(path)`` its streamed digest. Every candidate-controlled coordinate (a link target, a
    Work input path, a derived, HTML or PDF file) must first be a declared copied/derived entry of the export
    manifest (``pins``), then be admitted, and only then is it hashed; a coordinate that is not declared, is
    refused or is unreadable is a finite failure fact, never an open outside the candidate."""
    failures, summary = [], {'portable_documents': {}, 'manuscript_links': {}, 'work_inputs': {}}
    # THE SHAPE IS ADMITTED ONCE, BEFORE ANYTHING IS CONSUMED: a malformed container or field is a finite named failure and
    # none of the portable metadata is then read (the declared-entry and Fence path below only sees typed coordinates)
    problems = portable_shape_problems(report)
    if problems:
        failures.extend({'path': 'release/export-manifest.json', 'reason': 'portable metadata shape: ' + problem} for problem in problems)
        return failures, {**summary, 'portable_metadata_shape': 'malformed'}

    def pinned_bytes(rel, *, project, what, extra=None):
        """(sha256, None) for a declared, admitted, readable coordinate; (None, failure) otherwise."""
        row = {'project': project, 'path': rel if isinstance(rel, str) else repr(rel), **(extra or {})}
        if not isinstance(rel, str) or rel not in pins:
            return None, {**row, 'reason': what + ' is not a declared copied or derived entry of this export'}
        path, problem = admit(rel)
        if problem:
            return None, {**row, 'reason': what + ' refused by the read fence: ' + problem}
        read, problem = identity(path)
        if problem:
            return None, {**row, 'reason': what + ' ' + problem}
        return read['sha256'], None

    for project, doc in (report.get('portable_documents') or {}).items():
        for row in doc.get('files') or []:
            observed, failure = pinned_bytes(row.get('derived'), project=project, what='portable derived file')
            if failure:
                failures.append(failure)
            if row.get('source') is not None and pins.get(row['source']) != row.get('source_sha256'):
                failures.append({'project': project, 'path': str(row.get('source')), 'reason': 'portable copy was derived from bytes other than the exported source'})
        for key in ('html', 'appendix'):
            if doc.get(key):
                _observed, failure = pinned_bytes(doc[key], project=project, what='portable ' + key)
                if failure:
                    failures.append(failure)
        if doc.get('pdf'):
            observed, failure = pinned_bytes((doc['pdf'] or {}).get('path'), project=project, what='declared portable PDF')
            if failure:
                failures.append(failure)
            elif observed != (doc['pdf'] or {}).get('sha256'):
                failures.append({'project': project, 'path': doc['pdf']['path'], 'reason': 'declared portable PDF bytes differ from the export manifest'})
        summary['portable_documents'][project] = {'pdf': bool(doc.get('pdf')), 'files': len(doc.get('files') or []), 'compiler': (doc.get('compiler') or {}).get('ok')}
    for project, links in (report.get('manuscript_links') or {}).items():
        counts = {}
        for row in links.get('targets') or []:
            counts[row.get('status')] = counts.get(row.get('status'), 0) + 1
            if row.get('status') not in LINK_STATUSES:
                failures.append({'project': project, 'link': row.get('key'), 'reason': 'unknown link status ' + str(row.get('status'))})
            elif row['status'] == 'packaged':
                observed, failure = pinned_bytes(row.get('target'), project=project, what='packaged link target', extra={'link': row.get('key')})
                if failure:
                    failures.append(failure)
                elif row.get('kind') == 'artifact' and observed != row.get('admitted_sha256', row.get('expected_sha256')):
                    failures.append({'project': project, 'link': row.get('key'), 'path': row['target'], 'reason': 'packaged artifact bytes differ from the link pin'})
            elif not row.get('reason'):
                failures.append({'project': project, 'link': row.get('key'), 'reason': 'a link that is not packaged must state why'})
        summary['manuscript_links'][project] = counts
    for project, work in (report.get('work_inputs') or {}).items():
        counts = {}
        for row in work.get('rows') or []:
            counts[row.get('disposition')] = counts.get(row.get('disposition'), 0) + 1
            if row.get('disposition') in ('selected', 'supplementary'):
                observed, failure = pinned_bytes(row.get('path'), project=project, what='a Work input declared to travel')
                if failure:
                    failures.append(failure)
                elif row.get('reviewed') and observed != row.get('review_pin'):
                    failures.append({'project': project, 'path': row['path'], 'reason': 'a reviewed Work input declared to travel does not hold its review pin in the export'})
        summary['work_inputs'][project] = counts
    return failures, summary
