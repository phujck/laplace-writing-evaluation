"""The P1 Work port against the real Work owner over a real loopback socket.

The guarded case serves the existing HTTP door (project_work_surface.handle, the /work/* routes the app uses) over a
synthetic workspace on 127.0.0.1, publishes its URL beside the guarded run, and waits for the node renderer cases
(tests/work_port.test.mjs, run as a separate process that imports no Laplace code) to drive both renderers through
it. It then reads the ledger itself: every effect the renderers claim is the Work owner's own row, a refused attempt
wrote nothing, and a lost response was not resent.
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from laplace.work import project_work as w

PROJECT = 'p1-port'
WORKS = {'W-card': 'Card title', 'W-outline': 'Outline title', 'W-stale': 'Stale title', 'W-lost': 'Lost title',
         'W-capture': 'Capture title', 'W-compare': 'Compare title'}
WAIT_SECONDS = 300


def test_work_port_renderers_drive_the_real_work_owner_over_http(tmp_path):
    from laplace.web import project_work_surface, shared_ui
    snapshot = shared_ui.capture_asset_snapshot()
    assert {'work-port.mjs', 'work-port-outline.mjs'} <= set(snapshot.assets)   # served beside their importers
    home = Path(os.environ.get('TMPDIR') or tmp_path).parent
    root = tmp_path / 'workspace'
    (root / 'contract').mkdir(parents=True)
    for ident, title in WORKS.items():
        w.task(PROJECT, {'id': ident, 'title': title, 'goal': 'Purpose of ' + title}, root)
    posts = []

    class Door(BaseHTTPRequestHandler):
        def _serve(self, method):
            parts = urlsplit(self.path)
            body = self.rfile.read(int(self.headers.get('Content-Length') or 0)) if method == 'POST' else b''
            code, kind, raw = project_work_surface.handle(parts.path, parse_qs(parts.query), method, body, repo_root=root)
            if method == 'POST':
                posts.append({'path': parts.path, 'code': code, 'body': json.loads(body or b'{}')})
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self._serve('GET')

        def do_POST(self):
            self._serve('POST')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Door)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    done = home / 'work-port-node-report.json'
    try:
        (home / 'work-port-server.json').write_text(json.dumps({'url': 'http://127.0.0.1:%d' % server.server_address[1], 'project': PROJECT}))
        deadline = time.monotonic() + WAIT_SECONDS
        while not done.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert done.exists(), 'the node renderer cases did not report'
        time.sleep(0.5)   # the reporter writes once at the end of its run
        report = json.loads(done.read_text())
    finally:
        server.shutdown()
        server.server_close()
    # every node case that ran passed; the ledger is checked for exactly the cases that ran (a run may select some)
    assert report['failed'] == 0 and report['passed'] >= 1, report
    tasks = w._tasks(PROJECT, root)
    rows = [row for row in w._rows(root) if row.get('project') == PROJECT and row.get('record') == 'project-work']
    by_work = {ident: [row for row in rows if row['id'] == ident] for ident in WORKS}
    sent = lambda ident: [post for post in posts if post['body'].get('id') == ident]
    if 'card_title' in report:   # both renderers reached the owner: one recorded specification row each, with the typed title
        assert tasks['W-card']['title'] == report['card_title'] and len(by_work['W-card']) == 2
        assert tasks['W-outline']['title'] == report['outline_title'] and len(by_work['W-outline']) == 2
    if 'stale_original_guard' in report:   # the stale attempt was refused and wrote nothing; the external edit and the adopted attempt did
        stale = sent('W-stale')
        assert [post['code'] for post in stale] == [201, 409, 201], stale
        assert stale[1]['body']['expected_work_revision'] == report['stale_original_guard'] != stale[2]['body']['expected_work_revision']
        assert tasks['W-stale']['title'] == report['stale_final_title'] and len(by_work['W-stale']) == 3
    if 'lost_title' in report:   # the lost response: exactly one POST reached the owner and its effect is the one row
        lost = sent('W-lost')
        assert len(lost) == 1 and lost[0]['code'] == 201 and tasks['W-lost']['title'] == report['lost_title'] and len(by_work['W-lost']) == 2
    if 'capture_title' in report:   # P1-R2/R2a: the lost save, then the other writer; capture, new card and reinspection posted nothing
        capture = sent('W-capture')
        assert [post['code'] for post in capture] == [201, 201], capture
        assert capture[0]['body']['title'] == report['capture_title'] and capture[1]['body']['title'] == report['capture_external_title']
        assert tasks['W-capture']['title'] == report['capture_external_title'] and len(by_work['W-capture']) == 3
    if 'compare_final_title' in report:   # P1-R3: three other-writer edits, then one save on the displayed, adopted basis; no stale post
        compare = sent('W-compare')
        assert [post['code'] for post in compare] == [201, 201, 201, 201], compare
        assert compare[-1]['body']['title'] == report['compare_final_title'] == tasks['W-compare']['title'] and len(by_work['W-compare']) == 5
    assert len(posts) == report['posts_issued']
