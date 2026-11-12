"""Tests for the offline launcher (the ONE launch authority for the local interface).

The load-bearing invariants, all reachable WITHOUT network, a real browser, or a
real scanner spawn: preflight() reports the fixed capability key-shape; free_port
on a port nothing listens on is a clean no-op (never raises); and main's parser
carries the ruled defaults (port 8770, the dashboard landing page (/) in the default urls).
"""

from __future__ import annotations

import json
import socket

from laplace.desktop import offline_launcher


# ---------------------------------------------------------------------------
# preflight - the capability table's shape (no network, no side effects)
# ---------------------------------------------------------------------------

def test_preflight_returns_expected_key_shape():
    caps = offline_launcher.preflight()
    assert set(caps) == {"pdflatex", "latexmk", "pdftoppm", "pdftotext", "embed_model"}
    for key, val in caps.items():
        assert isinstance(val, bool), f"{key} should be a bool, got {type(val)}"


# ---------------------------------------------------------------------------
# free_port - a no-op on a quiet port (never an exception)
# ---------------------------------------------------------------------------

def _free_port_number() -> int:
    """An ephemeral port the OS just handed us, then released - nothing listens on it."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_free_port_on_idle_port_is_a_noop():
    port = _free_port_number()
    # nothing is listening -> zero reaped, no exception
    reaped = offline_launcher.free_port(port)
    assert reaped == 0


# ---------------------------------------------------------------------------
# main's parser - the ruled defaults
# ---------------------------------------------------------------------------

def test_parser_defaults_to_port_8770_and_dashboard_landing():
    args = offline_launcher.build_parser().parse_args([])
    assert args.port == 8770
    assert args.spawn_browser is True
    assert args.urls is None  # main() derives the landing default when urls is None
    assert args.tabs == "always"  # a deliberate launch (review.bat) gets its tab
    assert args.force_restart is False

    # W5: the landing is the dashboard at / (the /guide explainer died; GUIDE_PATH → "/").
    default_urls = args.urls if args.urls else [f"http://127.0.0.1:{args.port}{offline_launcher.GUIDE_PATH}"]
    assert default_urls == ["http://127.0.0.1:8770/"]


def test_parser_no_browser_and_repeated_url():
    args = offline_launcher.build_parser().parse_args(
        ["--no-browser", "--port", "9001", "--url", "http://x/a", "--url", "http://x/b"]
    )
    assert args.spawn_browser is False
    assert args.port == 9001
    assert args.urls == ["http://x/a", "http://x/b"]


def test_parser_tabs_cold_and_restart():
    args = offline_launcher.build_parser().parse_args(["--tabs", "cold", "--restart"])
    assert args.tabs == "cold"
    assert args.force_restart is True


# ---------------------------------------------------------------------------
# the idempotent launch (2026-07-15, "a million tabs"): the tab policy is pure,
# the port probe is read-only, and a cold port classifies as cold.
# ---------------------------------------------------------------------------

def test_should_open_tabs_policy_matrix():
    """cold-policy tabs open ONLY on a cold start - the whole fix. A reused or
    restarted (stale) scanner already has its tabs sitting in the browser."""
    should = offline_launcher._should_open_tabs
    assert should("always", "cold") and should("always", "fresh") and should("always", "stale")
    assert not should("never", "cold") and not should("never", "fresh")
    assert should("cold", "cold")
    for state in ("fresh", "stale", "wedged", "foreign", "unknown"):
        assert not should("cold", state), f"cold policy must not open tabs on state={state}"


def test_scanner_status_cold_on_idle_port():
    status = offline_launcher.scanner_status(_free_port_number())
    assert status["state"] == "cold"


def test_scanner_status_foreign_on_non_scanner_listener():
    """A listener whose cmdline is not laplace.web.scanner (here: this pytest process)
    classifies as foreign - the reclaim case. scanner_status itself must stay
    read-only: the probe classifies, it never kills."""
    import http.server
    import threading

    srv = http.server.HTTPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        status = offline_launcher.scanner_status(port)
        # psutil may be unable to attribute the pid on some CI boxes -> "unknown"
        # is the honest degradation; anything else must be "foreign".
        assert status["state"] in ("foreign", "unknown")
        # read-only: the server must still be alive after the probe
        assert offline_launcher._http_alive(port)
    finally:
        srv.shutdown()
        srv.server_close()


def test_code_mtime_positive_on_real_tree():
    assert offline_launcher._code_mtime() > 0


# ---------------------------------------------------------------------------
# _scanner_env - the PSU guard AS AMENDED. WO-20260715-233320-psu-embed-off put
# the local serving path at OFF (budget 0); THE CAPACITY AMENDMENT (his ruling
# 2026-07-23) supersedes that posture: "let's actually give ourselves the
# capacity we need rather than crippling ourselves". The launcher therefore
# DEFAULTS a SMALL SERIAL drip - LAPLACE_EMBED_BUDGET=6 on ONE thread, a few
# seconds of single-core work per call - with the loud per-batch DRIP lines in
# embed_router as the tripwire, and 0 still one env var away. setdefault means
# an explicit env still wins. UTF-8 stdio stays forced.
# ---------------------------------------------------------------------------

def test_scanner_env_defaults_embed_budget_off(monkeypatch):
    """The amended default: budget '6' x threads '1' - the small serial drip the Capacity
    Amendment ruled in (2026-07-23), replacing the '0' OFF posture and nothing like the old '128'
    that starved the box 30-60s on first clicks (WALK_2026-07-15 F1). Forced UTF-8 stays."""
    monkeypatch.delenv("LAPLACE_EMBED_BUDGET", raising=False)
    monkeypatch.delenv("LAPLACE_EMBED_THREADS", raising=False)
    env = offline_launcher._scanner_env()
    assert env["LAPLACE_EMBED_BUDGET"] == "6"          # the Capacity Amendment drip (never 128; 0 is one env var away)
    assert env["LAPLACE_EMBED_THREADS"] == "1"         # SERIAL: one thread, never a parallel burst
    assert env["PYTHONUTF8"] == "1" and env["PYTHONIOENCODING"] == "utf-8"


def test_scanner_env_explicit_budget_still_wins(monkeypatch):
    """setdefault semantics unchanged: an explicit env (a remote/supervised caller deliberately
    dripping, or unsetting for unlimited) overrides the OFF default -- the launcher never clobbers
    an intentional posture."""
    monkeypatch.setenv("LAPLACE_EMBED_BUDGET", "256")
    monkeypatch.setenv("LAPLACE_EMBED_THREADS", "8")
    env = offline_launcher._scanner_env()
    assert env["LAPLACE_EMBED_BUDGET"] == "256"        # explicit wins over the 0 default
    assert env["LAPLACE_EMBED_THREADS"] == "8"


# ---------------------------------------------------------------------------
# offer_state - W6.1: warm the cheap, OFFER the expensive, FIRE nothing expensive
# (the PSU law). Uses a fixture repo + fixture manifest and the REAL ensure_state.py
# so the proof is subprocess-level: the expensive rebuild's marker must never appear.
# ---------------------------------------------------------------------------

def _write_manifest(root, entries) -> None:
    (root / "localstate.json").write_text(
        json.dumps({"version": 1, "entries": entries}), encoding="utf-8")


def test_offer_state_warms_cheap_and_offers_expensive_without_firing_it(tmp_path, capsys):
    """The load-bearing W6.1 invariant, proven at the subprocess level:
      * a CHEAP entry whose check fails is rebuilt (its marker appears) -- the cheap warm ran;
      * an EXPENSIVE entry whose check fails is OFFERED (name + exact fix command printed) but
        its rebuild is NEVER invoked (its marker never appears) -- the PSU law holds.
    """
    # manifest commands are POSIX semantics on EVERY platform (core.process), so the
    # paths must be POSIX too: a raw WindowsPath interpolation feeds backslashes to the
    # POSIX shell, which eats them (found by the 2026-07-15 local pull-back walk - this
    # test could only pass in the Linux container it was written in).
    cheap_marker = tmp_path / "cheap_rebuilt.marker"
    expensive_marker = tmp_path / "expensive_rebuilt.marker"
    _write_manifest(tmp_path, [
        {
            "name": "cheap-warm",
            "cost": "cheap",
            "check": f"test -f {cheap_marker.as_posix()}",   # fails first -> the cheap warm rebuilds it
            "rebuild": f"touch {cheap_marker.as_posix()}",
        },
        {
            "name": "expensive-nodemap",
            "cost": "expensive",
            "check": "false",                                # always MISSING -> must be OFFERED
            "rebuild": f"touch {expensive_marker.as_posix()}",  # must NEVER run at launch
        },
    ])

    result = offline_launcher.offer_state(
        root=tmp_path, manifest=tmp_path / "localstate.json")

    # the cheap warm fired
    assert cheap_marker.exists(), "the cheap entry was not warmed by --cheap-only"
    # the expensive rebuild NEVER fired -- the whole point
    assert not expensive_marker.exists(), "an expensive rebuild was auto-fired at launch (PSU law broken)"

    # the expensive miss is surfaced as an OFFER: name + exact fix command
    assert result["offers"] == [{"name": "expensive-nodemap", "fix": f"touch {expensive_marker.as_posix()}"}]
    out = capsys.readouterr().out
    assert "OFFERED, not fired" in out
    assert "expensive-nodemap" in out
    assert f"touch {expensive_marker.as_posix()}" in out  # the fix command is printed for a deliberate fire


def test_offer_state_no_offer_when_expensive_present(tmp_path, capsys):
    """An expensive entry whose check PASSES is not offered (present+fresh)."""
    _write_manifest(tmp_path, [
        {"name": "present-map", "cost": "expensive", "check": "true", "rebuild": "false"},
    ])

    result = offline_launcher.offer_state(root=tmp_path, manifest=tmp_path / "localstate.json")

    assert result["offers"] == []
    assert "nothing to offer" in capsys.readouterr().out


def test_offer_state_env_disabled_is_a_clean_skip(tmp_path, monkeypatch):
    """LAPLACE_STATE_OFFER=0 skips the whole offer (the remote/CI escape hatch), and even then
    nothing expensive is fired."""
    expensive_marker = tmp_path / "should_never.marker"
    _write_manifest(tmp_path, [
        {"name": "x", "cost": "expensive", "check": "false", "rebuild": f"touch {expensive_marker.as_posix()}"},
    ])
    monkeypatch.setenv("LAPLACE_STATE_OFFER", "0")

    result = offline_launcher.offer_state(root=tmp_path, manifest=tmp_path / "localstate.json")

    assert result == {"skipped": True}
    assert not expensive_marker.exists()


def test_offer_state_missing_manifest_degrades_not_raises(tmp_path, capsys):
    """A missing manifest is a printed WARN + empty offer, never an exception (a launch is never
    sunk by the offer step)."""
    result = offline_launcher.offer_state(root=tmp_path, manifest=tmp_path / "nope.json")

    assert result["offers"] == []
    assert "error" in result
    assert "unreadable" in capsys.readouterr().out


def test_offer_state_real_manifest_never_fires_expensive(tmp_path, capsys):
    """Against the REAL localstate.json (repo root): the offer runs, warms the cheap, and every
    expensive entry (the nodemap-* / rounds-* per-project entries, the caches) is only ever
    check-only here -- no rebuild subprocess for any expensive entry is spawned. Proven by the
    offer's own contract: expensive names may appear under OFFERED, never as 'rebuilding:'."""
    result = offline_launcher.offer_state()  # defaults to repo root + real manifest
    out = capsys.readouterr().out
    # the offer step ran and produced a structured result over the real manifest
    assert "offers" in result and "cheap_verdict" in result
    # the launcher's offer NEVER prints ensure_state's rebuild line for an expensive entry
    assert "rebuilding:" not in out
    # if anything is offered it is the expensive per-project / cache state, with a fix command
    for o in result["offers"]:
        assert o["fix"], f"offer {o['name']} carries no fix command"
