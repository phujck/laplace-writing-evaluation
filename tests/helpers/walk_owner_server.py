"""The real HTTP owners on a disposable synthetic book project, for composed browser tests of the walk
(M5 S2). The project is tests/test_manuscript_structure._section_fixture in a temporary root; the server is
scanner.make_handler() on an ephemeral loopback port. Prints one JSON line {port, root} and serves until
stdin closes, then removes the root. No provider, model or network call is made by this process.
Started by tests/helpers/owner_browser.mjs for tests/walk_composed.playwright.mjs and
tests/workspace_episode.playwright.mjs."""
import json
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with tempfile.TemporaryDirectory(prefix='walk-owners-') as raw:
    root = Path(raw)
    os.environ.update(LAPLACE_REPO_ROOT=str(root), LAPLACE_NO_PREWARM='1', LAPLACE_TEST_PROCESS='1')
    from test_manuscript_structure import _section_fixture
    _section_fixture(root)
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(json.dumps({'port': httpd.server_address[1], 'root': str(root)}), flush=True)
    sys.stdin.read()
    httpd.shutdown()
    httpd.server_close()
