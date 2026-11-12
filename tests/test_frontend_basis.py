"""P2 page-issued frontend basis over two real frozen asset snapshots.

Snapshot A is the actual allowlisted assets and the actual project/walk templates; snapshot B is the same assets with
the actual project template plus one appended comment line (a newer frontend). Each is served by its own writing
handler (scanner.make_handler, the real /project and /authoring/health routes). The issued page names the snapshot it
was served from, the captured template itself is unchanged (no self-hash), a template without </head> keeps an
unknown basis, and B's health names the newer served basis. The two bases are published beside the guarded run for the
page-side cases (tests/frontend_basis.test.mjs, a separate process that imports no Laplace code).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from laplace.web import scanner, shared_ui

TEMPLATES = Path(shared_ui.__file__).parent


def get(handler_type, path):
    """One GET through the real writing handler's routing (the existing asset-snapshot test's pattern)."""
    handler = handler_type.__new__(handler_type)
    handler.path = path
    responses = []
    handler._send = lambda status, body, ctype: responses.append((status, ctype, body))
    handler.do_GET()
    assert len(responses) == 1
    return responses[0]


def test_issued_page_names_its_frozen_snapshot_and_a_newer_served_basis_is_discriminated(tmp_path):
    actual = {'project': TEMPLATES / 'pipeline.html', 'walk': TEMPLATES / 'walk.html'}
    newer = tmp_path / 'pipeline.html'
    newer.write_bytes(actual['project'].read_bytes() + b'<!-- a newer frontend -->\n')
    a = shared_ui.capture_asset_snapshot(templates=actual)
    b = shared_ui.capture_asset_snapshot(templates={**actual, 'project': newer})
    assert a.digest != b.digest and set(a.assets) == set(b.assets)
    assert {'owner-request.mjs', 'selected-lifetime.mjs', 'frontend-basis.mjs'} <= set(a.assets)

    issued = shared_ui.issued_page(a, 'project')
    meta = re.findall(rb'<meta name="laplace-frontend-basis" content="([0-9a-f]{64})">', issued)
    assert meta == [a.digest.encode()]
    assert issued.replace(b'<meta name="laplace-frontend-basis" content="' + a.digest.encode() + b'">\n', b'') == a.pages['project']
    assert b'laplace-frontend-basis' not in a.pages['project']                 # the captured template is unchanged
    assert shared_ui.capture_asset_snapshot(templates=actual).digest == a.digest   # serving never alters the basis

    (tmp_path / 'old.html').write_bytes(b'<main>an older page</main>')
    blind = shared_ui.capture_asset_snapshot(templates={**actual, 'project': tmp_path / 'old.html'})
    assert shared_ui.issued_page(blind, 'project') == b'<main>an older page</main>'   # no head: the basis stays unknown

    status, ctype, body = get(scanner.make_handler(shared_assets=a), '/project?workspace=writing&corpus=book')
    assert status == 200 and ctype.startswith('text/html') and body == issued
    health_a = json.loads(get(scanner.make_handler(shared_assets=a), '/authoring/health')[2])
    health_b = json.loads(get(scanner.make_handler(shared_assets=b), '/authoring/health')[2])
    assert health_a['frontend_bundle']['sha256'] == a.digest and health_b['frontend_bundle']['sha256'] == b.digest

    home = Path(os.environ.get('TMPDIR') or tmp_path).parent
    (home / 'frontend-basis.json').write_text(json.dumps({'issued': meta[0].decode(), 'served_newer': health_b['frontend_bundle']['sha256'],
                                                          'served_same': health_a['frontend_bundle']['sha256']}))
