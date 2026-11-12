"""The front door's read core (front door M1): registry, query layer, trace reader, door.

Four modules, one law each, and this file is the acceptance test for all four:

* ``laplace.engine.sources``  — the registry is the ONE extension point; an unknown name is a
  loud absence, never an exception, and a ``scan=False`` store is refused by the row
  explorer in words (the 54 MB lesson: row counts are small, row BYTES are not).
* ``laplace.engine.rows``     — an append-only store ACQUIRES bad lines and partial final
  writes; a reader that halts on one goes dark exactly when it is needed. Malformed
  lines are skipped and COUNTED; byte offsets are the addressable row id.
* ``laplace.engine.trace``    — the journal is already a span log: pairing, durations from ts,
  orphans surfaced with their kind, and in-flight vs died as DIFFERENT states.
* ``laplace.web.front_door`` — ``handle(path, query, method, body)``; GET only at M1, and
  ``None`` means "not mine, fall through".

No live server anywhere here: every test calls the functions and ``handle`` directly,
over tmp_path fixtures pointed at through the registry.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from laplace.web import front_door
from laplace.engine import rows, sources, trace

#: above Linux's pid_max ceiling (2^22) — a pid that CANNOT be alive, which is what
#: makes the "died" state assertable without racing a real process.
DEAD_PID = 2147483647


# --------------------------------------------------------------------------- helpers

def _write_lines(path: Path, lines: list[str], partial: str | None = None) -> list[int]:
    """Write JSONL text verbatim and return each full line's START byte offset.

    ``partial`` is appended WITHOUT a trailing newline — a store caught mid-append,
    which is the state every reader here must survive.
    """
    text = "".join(line + "\n" for line in lines)
    if partial is not None:
        text += partial
    path.write_bytes(text.encode("utf-8"))
    offsets, at = [], 0
    for line in lines:
        offsets.append(at)
        at += len(line.encode("utf-8")) + 1
    return offsets


def _point(monkeypatch, name: str, path: Path) -> None:
    """Aim one registry source at a fixture file (the packet's documented seam)."""
    monkeypatch.setitem(sources.SOURCES[name], "path", str(path))


# --------------------------------------------------------------------------- sources

def test_an_absolute_fixture_path_wins_the_registry_join(tmp_path, monkeypatch):
    """The seam every other test in this file stands on, asserted once before it is
    trusted: ``get`` joins repo_root/path, and an ABSOLUTE path wins that join."""
    f = tmp_path / "journal.jsonl"
    f.write_text("", encoding="utf-8")
    _point(monkeypatch, "journal", f)
    assert sources.get("journal")["abspath"] == str(f)


def test_get_serves_the_resolved_entry_and_unknown_names_serve_none(tmp_path, monkeypatch):
    f = tmp_path / "journal.jsonl"
    _write_lines(f, ['{"record": "act", "act_id": "A1"}'])
    _point(monkeypatch, "journal", f)

    spec = sources.get("journal")
    assert spec["name"] == "journal" and spec["scan"] is True
    assert spec["host_owned"] is False
    assert spec["id_field"] == "act_id" and spec["ts_field"] == "ts"
    assert "record" in spec["columns"] and isinstance(spec["facets"], list)
    assert sources.get("no-such-source") is None


def test_stat_serves_liveness_and_absence_loudly(tmp_path, monkeypatch):
    f = tmp_path / "journal.jsonl"
    _write_lines(f, ['{"record": "act"}'])
    _point(monkeypatch, "journal", f)
    st = sources.stat("journal")
    assert st["bytes"] == f.stat().st_size and st["red"] is False
    assert st["age_s"] < 60 and st["budget_s"] == sources.SOURCES["journal"]["staleness"]
    assert st["scan"] is True

    # a missing store is ABSENT and RED — rendered as loudly as failure, never raised
    _point(monkeypatch, "predictions", tmp_path / "nowhere.jsonl")
    gone = sources.stat("predictions")
    assert gone["absent"] is True and gone["red"] is True and "label" in gone

    assert sources.stat("no-such-source") == {"name": "no-such-source",
                                              "error": "unknown source"}


def test_roster_covers_the_whole_registry_in_order():
    roster = sources.roster()
    assert [r["name"] for r in roster] == list(sources.SOURCES)
    assert all("red" in r for r in roster), "every row carries a freshness verdict"


def test_retired_closure_meter_is_not_an_active_stale_source():
    # Its producer was removed on Sep 16. The retained history is no longer a live organ.
    assert sources.get("closure_meter") is None
    assert "closure_meter" not in sources.SOURCES


def test_a_metadata_only_source_is_refused_by_the_row_explorer_in_words(monkeypatch, tmp_path):
    monkeypatch.setitem(sources.SOURCES, "metadata_fixture", {
        "path": tmp_path / "large-history.jsonl", "scan": False,
        "description": "metadata-only history fixture", "freshness": None,
    })
    res = rows.query("metadata_fixture")
    assert res["rows"] == [] and "metadata-only" in res["error"]
    assert list(rows.scan("metadata_fixture")) == []
    assert rows.scan_report("metadata_fixture") == {"name": "metadata_fixture", "scanned": False}


# --------------------------------------------------------------------------- filtering

def _matches(expr: str, row: dict) -> bool:
    predicate, _parsed = rows.compile_filter(expr)
    return predicate(row)


def test_tier_one_bare_words_match_the_serialized_row():
    row = {"record": "act", "act": "the metric redistill"}
    assert _matches("redistill", row)
    assert _matches("RECORD", row), "case-insensitive over the serialized row"
    assert not _matches("bequest", row)


def test_tier_two_key_value_and_negation():
    row = {"record": "act", "status": "pass"}
    assert _matches("record:act", row)
    assert not _matches("record:bank", row)
    assert _matches("-record:bank", row)
    assert not _matches("-record:act", row)
    assert _matches("-record:act status:pass", row) is False, "terms AND together"


def test_tier_two_numeric_comparison():
    assert _matches("wall_s:>10", {"wall_s": 12})
    assert not _matches("wall_s:>10", {"wall_s": 3})
    assert _matches("wall_s:<10", {"wall_s": 3})
    assert not _matches("wall_s:>10", {"wall_s": "not a number"}), (
        "an uncomparable value fails the predicate, it never raises")


def test_tier_two_quoted_phrase_protects_spaces():
    assert _matches('"the long march"', {"title": "the long march north"})
    assert not _matches('"the long march"', {"title": "the march"}), (
        "unquoted this would be three ANDed words; quoted it is one phrase")


def test_tier_two_prefix_star():
    assert _matches("id:WO-2026*", {"id": "WO-20260824-front-door"})
    assert not _matches("id:WO-2026*", {"id": "ASK-20260824-1"})


def test_dotted_paths_reach_into_nested_rows():
    row = {"phases": {"metric_redistill": {"status": "green"}}}
    assert _matches("phases.metric_redistill.status:green", row)
    assert rows.flatten(row)["phases.metric_redistill.status"] == "green"


def test_the_parsed_sentence_is_echoed_back_for_every_tier():
    _p, parsed = rows.compile_filter("record:act -status:fail redistill")
    assert "record matching act" in parsed
    assert "status not matching fail" in parsed
    assert "redistill" in parsed and " AND " in parsed
    assert rows.compile_filter("")[1] == "all rows"


def test_truncate_row_keeps_the_structure_and_drops_the_bulk():
    big = "x" * (rows.TRUNCATE_AT + 500)
    out = rows.truncate_row({"id": "W1", "text": big, "nested": {"also": big}})
    assert out["id"] == "W1"
    assert out["text"] == {"truncated": True, "bytes": len(big), "head": big[:200]}
    assert out["nested"]["also"]["truncated"] is True, "nesting is walked, not flattened"
    assert rows.truncate_row({"text": "x" * rows.TRUNCATE_AT})["text"] == "x" * rows.TRUNCATE_AT


# --------------------------------------------------------------------------- scanning

@pytest.fixture
def torn_journal(tmp_path, monkeypatch):
    """A store with a mid-file malformed line AND a partial final write — the two
    states an append-only file actually reaches in the wild."""
    good = ['{"record": "act", "act_id": "A1", "mark": "first"}',
            '{"record": "step", "act_id": "A1", "mark": "second"}',
            '{"record": "act", "act_id": "A1", "mark',            # torn line, newline-terminated
            '{"record": "bank", "act_id": "A1", "mark": "third"}']
    f = tmp_path / "journal.jsonl"
    offs = _write_lines(f, good, partial='{"record": "act", "act_id": "A2"')
    _point(monkeypatch, "journal", f)
    return f, offs


def test_scan_yields_parseable_rows_with_their_start_offsets(torn_journal):
    _f, offs = torn_journal
    got = list(rows.scan("journal"))
    assert [r["mark"] for _o, r in got] == ["first", "second", "third"]
    assert [o for o, _r in got] == [offs[0], offs[1], offs[3]], (
        "the offset is the LINE'S START — the addressable fallback row id")


def test_scan_report_counts_the_lines_it_could_not_parse(torn_journal):
    rep = rows.scan_report("journal")
    assert rep["scanned"] is True and rep["rows"] == 3
    # the torn MID-FILE line is malformed; the newline-less final write is a moment
    # mid-append, surfaced as partial_tail, never a permanent-looking defect count
    # (the build wave's observation, folded into rows.scan_report)
    assert rep["malformed"] == 1
    assert rep["partial_tail"] is True


def test_scan_since_resumes_and_a_shrunken_store_restarts_from_zero(torn_journal):
    _f, offs = torn_journal
    assert [r["mark"] for _o, r in rows.scan("journal", since=offs[1])] == ["second", "third"]
    assert len(list(rows.scan("journal", since=10 ** 9))) == 3, (
        "a since past EOF is rotation, not the end of history")


def test_row_at_seeks_back_to_exactly_that_row(torn_journal):
    _f, offs = torn_journal
    assert rows.row_at("journal", offs[3])["mark"] == "third"
    assert rows.row_at("journal", offs[0])["act_id"] == "A1"
    assert rows.row_at("journal", offs[2]) is None, "the torn line answers None, loudly"
    assert rows.row_at("journal", 10 ** 9) is None


def test_query_pages_newest_first_and_truncates(torn_journal):
    res = rows.query("journal", "record:act")
    assert res["total"] == 3 and res["matched"] == 1
    assert res["rows"][0]["row"]["mark"] == "first"
    assert res["id_field"] == "act_id" and res["path"].endswith("journal.jsonl")
    assert rows.query("no-such-source")["rows"] == []
    assert "unknown source" in rows.query("no-such-source")["error"]


def test_find_by_id_takes_the_latest_row_for_a_duplicated_id(tmp_path, monkeypatch):
    f = tmp_path / "journal.jsonl"
    offs = _write_lines(f, ['{"act_id": "DUP", "gen": 1}',
                            '{"act_id": "OTHER", "gen": 0}',
                            '{"act_id": "DUP", "gen": 2}'])
    _point(monkeypatch, "journal", f)
    off, row = rows.find_by_id("journal", "DUP")
    assert row["gen"] == 2 and off == offs[2], "append-only: the LAST row wins"
    assert rows.find_by_id("journal", "nobody") is None


def test_facets_count_over_the_filtered_set(torn_journal):
    res = rows.facets("journal", "")
    assert dict(res["facets"]["record"])["act"] == 1
    assert dict(res["facets"]["record"])["step"] == 1
    # asserted DIRECTLY, never behind an `or`: guarded by "record not in facets" this
    # passed just as green when faceting under a filter returned nothing at all — the
    # exact regression the test is named for. A KeyError here is the correct failure.
    filtered = rows.facets("journal", "record:bank")["facets"]
    assert dict(filtered["record"]) == {"bank": 1}


# --------------------------------------------------------------------------- trace

@pytest.fixture
def act_journal(tmp_path, monkeypatch):
    """One closed act (paired step, orphan done, open step, bank, act_end), one act
    left open behind a dead pid, and one ambient bank."""
    lines = [
        json.dumps({"record": "act", "act_id": "A1", "act": "the closed act",
                    "pid": DEAD_PID, "ts": "2026-08-24T10:00:00Z"}),
        json.dumps({"record": "step", "act_id": "A1", "index": 1, "name": "gather",
                    "phase": "begin", "ts": "2026-08-24T10:00:01Z"}),
        json.dumps({"record": "step", "act_id": "A1", "index": 1, "name": "gather",
                    "phase": "done", "ts": "2026-08-24T10:00:03Z", "seconds": 99}),
        json.dumps({"record": "step", "act_id": "A1", "index": 2, "name": "orphaned",
                    "phase": "done", "ts": "2026-08-24T10:00:04Z"}),
        json.dumps({"record": "step", "act_id": "A1", "index": 3, "name": "still-open",
                    "phase": "begin", "ts": "2026-08-24T10:00:05Z"}),
        json.dumps({"record": "bank", "act_id": "A1", "store": "contract/promises.jsonl",
                    "row_id": "P-1", "phase": "begin", "ts": "2026-08-24T10:00:05Z"}),
        json.dumps({"record": "bank", "act_id": "A1", "store": "contract/promises.jsonl",
                    "row_id": "P-1", "phase": "done", "ts": "2026-08-24T10:00:06Z"}),
        json.dumps({"record": "adjudication", "act_id": "A1", "status": "accepted",
                    "note": "the judge signed", "ts": "2026-08-24T10:00:07Z"}),
        json.dumps({"record": "act_end", "act_id": "A1", "status": "pass",
                    "ts": "2026-08-24T10:00:10Z"}),
        json.dumps({"record": "bank", "act_id": None, "store": "contract/seats.jsonl",
                    "row_id": "AMB-1", "phase": "done", "ts": "2026-08-24T10:00:11Z"}),
        json.dumps({"record": "act", "act_id": "A2", "act": "the abandoned act",
                    "pid": DEAD_PID, "ts": "2026-08-24T09:00:00Z"}),
    ]
    f = tmp_path / "journal.jsonl"
    _write_lines(f, lines)
    _point(monkeypatch, "journal", f)
    return f


def test_the_dead_pid_is_genuinely_dead():
    assert not Path(f"/proc/{DEAD_PID}").exists(), (
        "the died-state assertion depends on this pid being impossible")


def test_acts_group_newest_first_with_ambient_last(act_journal):
    acts = trace.acts()
    assert [a["act_id"] for a in acts] == ["A1", "A2", trace.AMBIENT]
    a1, a2, amb = acts
    assert a1["state"] == "done" and a1["status"] == "pass"
    assert a1["duration_s"] == 10.0, "act duration from the act/act_end ts pair"
    assert a1["n_steps"] == 2 and a1["n_orphans"] == 1
    assert a1["n_banks"] == 1, "only the bank's DONE phase is an artifact"
    assert a2["state"] == "died", "an open act behind a dead pid is DIED, not in-flight"
    assert amb["act"] == trace.AMBIENT and amb["n_banks"] == 1


def test_act_tree_pairs_steps_and_computes_duration_from_ts(act_journal):
    a = trace.act_tree("A1")
    steps = {s["name"]: s for s in a["steps"]}
    assert steps["gather"]["duration_s"] == 2.0, (
        "the ts pair is the truth; the self-reported seconds field does not override it")
    assert steps["gather"]["open"] is False
    assert steps["still-open"]["open"] is True and steps["still-open"]["duration_s"] is None
    assert "orphaned" not in steps, "a done with no begin is never faked into a step"


def test_the_orphan_is_surfaced_with_its_kind(act_journal):
    (orphan,) = trace.act_tree("A1")["orphans"]
    assert orphan["kind"] == "step-done-without-begin"
    assert orphan["name"] == "orphaned" and isinstance(orphan["offset"], int)


def test_a_repeated_step_keeps_both_spans(tmp_path, monkeypatch):
    """A real act re-runs the same named step — a retry, a second pass, a loop. Keyed
    by ``(index, name)`` the second ``begin`` overwrote the first and a COMPLETED span
    vanished from the waterfall; steps are a LIST of spans, and a ``done`` closes the
    most recent still-OPEN match."""
    lines = [
        json.dumps({"record": "act", "act_id": "R1", "act": "the retrying act",
                    "pid": DEAD_PID, "ts": "2026-08-24T10:00:00Z"}),
        json.dumps({"record": "step", "act_id": "R1", "index": 1, "name": "fetch",
                    "phase": "begin", "ts": "2026-08-24T10:00:01Z"}),
        json.dumps({"record": "step", "act_id": "R1", "index": 1, "name": "fetch",
                    "phase": "done", "ts": "2026-08-24T10:00:03Z"}),
        json.dumps({"record": "step", "act_id": "R1", "index": 1, "name": "fetch",
                    "phase": "begin", "ts": "2026-08-24T10:00:04Z"}),
        json.dumps({"record": "step", "act_id": "R1", "index": 1, "name": "fetch",
                    "phase": "done", "ts": "2026-08-24T10:00:09Z"}),
        json.dumps({"record": "act_end", "act_id": "R1", "status": "pass",
                    "ts": "2026-08-24T10:00:10Z"}),
    ]
    f = tmp_path / "journal.jsonl"
    _write_lines(f, lines)
    _point(monkeypatch, "journal", f)

    a = trace.act_tree("R1")
    spans = [s for s in a["steps"] if s["name"] == "fetch"]
    assert len(spans) == 2, "a repeated step is two spans, never one overwritten slot"
    assert [s["duration_s"] for s in spans] == [2.0, 5.0], "begin order is preserved"
    assert all(s["open"] is False for s in spans), "each done closed its OWN span"
    assert a["orphans"] == [], "the second done is a pairing, never an orphan"
    assert trace.acts()[0]["n_steps"] == 2
    assert all({"index", "name", "begin", "end", "seconds", "duration_s", "open",
                "offset"} <= set(s) for s in spans), "the rendered shape is unchanged"


def test_banks_hang_under_their_act_and_null_act_ids_group_ambient(act_journal):
    (bank,) = trace.act_tree("A1")["banks"]
    assert bank["store"] == "contract/promises.jsonl" and bank["row_id"] == "P-1"
    (adj,) = trace.act_tree("A1")["adjudications"]
    assert adj["status"] == "accepted"

    amb = trace.act_tree(trace.AMBIENT)
    assert amb["state"] == "done" and amb["banks"][0]["row_id"] == "AMB-1"
    assert trace.act_tree("no-such-act") is None


# --------------------------------------------------------------------------- handle

def test_the_page_is_served_at_slash_front():
    """Unconditional: the page is the surface's primary deliverable, and a test that
    skips itself when the deliverable is missing turns GREEN on its absence."""
    status, ctype, body = front_door.handle("/front", {}, "GET", b"")
    assert status == 200 and ctype.startswith("text/html")
    assert isinstance(body, bytes) and body
    # The nav used to be hand-typed markup and this asserted the literal href. It is now
    # a render of /front/places, so the shell ships no place names at all — asserting
    # markup here would only re-check that someone typed a string. The invariant it was
    # really protecting (the atlas is reachable from the front door) is asserted below,
    # against the census, where reachability now actually lives.
    assert b'id="nav"' in body, "the shell must still carry the nav mount point"
    assert b"/front/places" in body, "the shell must fetch the places census"


def test_every_place_in_the_census_is_actually_served():
    """BOTH DIRECTIONS, and this is the guard that keeps the nav honest.

    A census row that names an unserved route puts a door in his header that opens onto
    nothing — a broken promise manufactured by the very table meant to remove them. The
    converse (a served page-class door with no census row) is how /front/walk stayed
    invisible all day while the server answered it.
    """
    from laplace.web import front_places

    census = front_places.census()
    assert census["places"], "the census is empty — the nav would render nothing"

    hrefs = {p["href"] for p in census["places"]}
    assert "/front/atlas" in hrefs, "the atlas is not reachable from the front door"
    assert "/front/walk" in hrefs, "the founding walk is not reachable from the front door"

    for place in census["places"]:
        href = place["href"]
        if not href.startswith("/front/"):
            continue                       # hash routes and /seats are not handle()'s
        status, _ctype, body = front_door.handle(href, {}, "GET", b"")
        assert status == 200, f"census names {href}, which the server answers {status}"
        assert body, f"census names {href}, which serves an empty body"


def test_no_place_may_render_a_number_without_a_unit():
    """The chip grammar. A census that starts returning prose has quietly become the
    fourth hand-maintained map, and "the label is the explanation" stops being true."""
    from laplace.web import front_places

    for place in front_places.census()["places"]:
        assert place.get("why"), f"{place['id']} does not say why he would go there"
        for chip in place.get("chips", []):
            assert set(chip) == {"n", "unit", "warn"}, f"chip grammar broken: {chip}"
            assert isinstance(chip["unit"], str) and chip["unit"]


def test_the_atlas_board_is_mounted_in_both_registers() -> None:
    status, ctype, body = front_door.handle(
        "/front/atlas", {"format": ["json"]}, "GET", b""
    )
    assert status == 200 and ctype.startswith("application/json")
    payload = json.loads(body)
    assert payload["board"] == "atlas"
    assert set(payload) >= {"campaign", "inventory", "walk", "live"}
    # The suite isolates LAPLACE_STATE, so the test store is intentionally undeclared;
    # the mount must surface that truth rather than borrowing the user's live state.
    assert "status" in payload["walk"]["migration"]
    assert payload["walk"]["migration"].get("walked") is not True

    status, ctype, body = front_door.handle("/front/atlas", {}, "GET", b"")
    assert status == 200 and ctype.startswith("text/html")
    assert b"the atlas board" in body and b"RENDER OF ROWS" in body


def test_rows_serves_json_to_an_agent(torn_journal):
    status, ctype, body = front_door.handle(
        "/front/rows", {"source": ["journal"], "format": ["json"], "limit": ["10"]},
        "GET", b"")
    assert status == 200 and ctype.startswith("application/json")
    payload = json.loads(body)
    assert payload["source"] == "journal" and payload["total"] == 3
    assert [m["row"]["mark"] for m in payload["rows"]] == ["third", "second", "first"]


def test_rows_serves_html_carrying_its_row_source_byline(torn_journal):
    status, ctype, body = front_door.handle(
        "/front/rows", {"source": ["journal"]}, "GET", b"")
    html = body.decode("utf-8")
    assert status == 200 and ctype.startswith("text/html")
    assert "[source]" in html and "journal.jsonl" in html, "no panel without its byline"
    assert "#record/journal/" in html, "every row carries its address"


def test_record_round_trips_a_row_by_its_offset(torn_journal):
    _f, offs = torn_journal
    status, ctype, body = front_door.handle(
        "/front/record", {"source": ["journal"], "off": [str(offs[3])]}, "GET", b"")
    html = body.decode("utf-8")
    assert status == 200 and ctype.startswith("text/html")
    # the record pane escapes its JSON before it renders it — markup never survives a row
    assert "&quot;mark&quot;: &quot;third&quot;" in html and f"row @{offs[3]}" in html

    _s, _c, missing = front_door.handle(
        "/front/record", {"source": ["journal"], "off": [str(offs[2])]}, "GET", b"")
    assert "no row at journal" in missing.decode("utf-8")

    _s, _c, unknown = front_door.handle(
        "/front/record", {"source": ["nope"]}, "GET", b"")
    assert "unknown source" in unknown.decode("utf-8")


def test_a_malformed_session_id_serves_the_bad_session_fragment():
    status, ctype, body = front_door.handle(
        "/front/chat", {"sid": ["../../etc/passwd"]}, "GET", b"")
    assert status == 200 and ctype.startswith("text/html")
    assert "bad session id" in body.decode("utf-8"), (
        "a non-uuid never reaches the host-owned transcript directory")


#: the surface contract is the door list's ONE authority — a route declared there and
#: not served by handle() must fail here, not be discovered by a reader in the browser.
_SURFACE_YAML = Path(__file__).resolve().parents[1] / "contract" / "surfaces" / "front.yaml"
#: /front/stream never rides handle() — the scanner dispatches it to stream.serve.
_NOT_VIA_HANDLE = {"/front/stream"}
#: /front/field is the one door that REQUIRES an offset: refusing a bare GET is its
#: declared behaviour, not a fall-through.
_BARE_GET_STATUS = {
    "/front/field": {400},
    "/front/serve": {200, 404, 409, 503},
    "/front/serve/body": {400},
    "/front/serve/source": {400},
}


def _declared_doors() -> list[str]:
    doors, in_reads = [], False
    for line in _SURFACE_YAML.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\w[\w_]*\s*:", line):
            in_reads = line.startswith("reads:")
            continue
        m = re.match(r"^\s*-\s*GET\s+(\S+)", line)
        if in_reads and m:
            doors.append(m.group(1))
    return doors


def test_the_contract_declares_the_doors_this_suite_walks():
    doors = _declared_doors()
    assert "/front" in doors and "/front/apex" in doors and "/front/stream" in doors
    assert len(doors) >= 13, "the reads: block of contract/surfaces/front.yaml"


@pytest.mark.parametrize("door", [d for d in _declared_doors()
                                  if d not in _NOT_VIA_HANDLE])
def test_every_declared_door_answers_a_bare_get(door):
    """Nine of thirteen declared doors were never exercised at all: an exception in
    any of them reached a scanner with no top-level handler and killed the request
    with no HTTP response. Every declared door answers, over the REAL stores."""
    got = front_door.handle(door, {}, "GET", b"")
    assert got is not None, f"{door} is declared in the contract but falls through"
    status, ctype, body = got
    allowed = _BARE_GET_STATUS.get(door, {200})
    assert status in allowed, f"{door} answered {status}; expected one of {sorted(allowed)}"
    assert isinstance(ctype, str) and isinstance(body, bytes)


def test_a_junk_limit_serves_the_default_instead_of_killing_the_request():
    """`?limit=abc` used to raise ValueError out of handle(); the scanner has no
    top-level try, so the connection died with no response at all."""
    for junk in ("abc", "-3", "", "9" * 5000):
        status, _c, body = front_door.handle(
            "/front/rows", {"source": ["journal"], "format": ["json"],
                            "limit": [junk]}, "GET", b"")
        assert status == 200 and json.loads(body)["source"] == "journal"
    assert front_door._qint({"limit": ["10000"]}, "limit", 50, 500) == 500, "capped"
    assert front_door._qint({}, "limit", 50, 500) == 50
    # a digit string past CPython's int() ceiling is junk too, not an offset
    assert front_door.handle("/front/record",
                             {"source": ["journal"], "off": ["9" * 5000]},
                             "GET", b"")[0] == 200


def test_unknown_paths_and_non_get_methods_fall_through():
    assert front_door.handle("/front/nope", {}, "GET", b"") is None
    assert front_door.handle("/", {}, "GET", b"") is None
    assert front_door.handle("/front", {}, "POST", b"{}") is None, (
        "M1 is the READ surface; the write half is M2, behind his walk")
    assert front_door.handle("/front/rows", {}, "PUT", b"") is None


# --------------------------------------------------------------------------- chat lines

def test_a_user_string_message_renders_escaped():
    html = front_door.render_chat_line(json.dumps(
        {"message": {"role": "user", "content": "run <script>alert(1)</script> please"}}))
    assert 'class="msg user"' in html and "run &lt;script&gt;" in html
    assert "<script>" not in html, "transcript text is data, never markup"


def test_an_assistant_list_message_renders_text_and_names_its_tools():
    html = front_door.render_chat_line(json.dumps({"message": {"role": "assistant", "content": [
        {"type": "text", "text": "reading the registry"},
        {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
    ]}}))
    assert "reading the registry" in html and "Bash" in html
    assert 'class="msg assistant"' in html


def test_tool_results_and_malformed_lines_render_nothing():
    assert front_door.render_chat_line(json.dumps({"message": {"role": "user", "content": [
        {"type": "tool_result", "content": "40 MB of output"}]}})) is None
    assert front_door.render_chat_line(b'{"message": {"role": "user"') is None
    assert front_door.render_chat_line(b"") is None
    assert front_door.render_chat_line(json.dumps({"summary": "no message key"})) is None
    assert front_door.render_chat_line(json.dumps(
        {"message": {"role": "system", "content": "hi"}})) is None
    assert front_door.render_chat_line(json.dumps(
        {"message": {"role": "assistant", "content": []}})) is None


# --------------------------------------------------------------------------- the ask-door

def _ask_fixture(tmp_path, monkeypatch):
    """A tmp repo root holding one open ASK row; the decide door banks against it."""
    (tmp_path / "corpus_friction").mkdir()
    (tmp_path / "contract").mkdir()
    store = tmp_path / "corpus_friction" / "work_orders.jsonl"
    store.write_text(json.dumps({"record": "note", "id": "ASK-20260824-test-perm",
                                 "text": "PERMISSION ASK - may I fire X", "ts": "2026-08-24T10:00:00Z"}) + "\n",
                     encoding="utf-8")
    monkeypatch.setattr(front_door, "_repo_root", lambda: tmp_path)
    return store


def test_the_ask_door_banks_his_decision_and_the_ask_retires(tmp_path, monkeypatch):
    store = _ask_fixture(tmp_path, monkeypatch)
    body = json.dumps({"ask": "ASK-20260824-test-perm", "decision": "approve",
                       "text": "yes, fire it"}).encode()
    status, ctype, payload = front_door.handle("/front/decide", {}, "POST", body)
    assert status == 200
    out = json.loads(payload)
    assert out["decision"] == "approved" and out["target"] == "ASK-20260824-test-perm"
    rows_now = [json.loads(line) for line in store.read_text().splitlines()]
    res = [r for r in rows_now if r.get("record") == "resolution"]
    assert len(res) == 1
    r = res[0]
    assert r["actor"] == "gerard" and r["via"] == "front-door"
    assert r["text"] == "yes, fire it"
    assert r["edges"] == [{"rel": "resolves", "target": "ASK-20260824-test-perm"}]
    # the ask lane retires on exactly this shape — recomputed from rows, no state
    from laplace.web import seats_surface
    assert seats_surface._pending_asks(tmp_path) == []
    # and the shared banking path journaled the act (kill-safe append)
    assert (tmp_path / "contract" / "journal.jsonl").exists()


def test_the_ask_door_refuses_junk_and_unknown_asks(tmp_path, monkeypatch):
    _ask_fixture(tmp_path, monkeypatch)
    s, _c, p = front_door.handle("/front/decide", {}, "POST", b"not json")
    assert s == 400 and b"JSON object" in p
    s, _c, p = front_door.handle("/front/decide", {}, "POST",
                                 json.dumps({"ask": "ASK-20260824-test-perm",
                                             "decision": "maybe"}).encode())
    assert s == 400 and b"approve or refuse" in p
    s, _c, p = front_door.handle("/front/decide", {}, "POST",
                                 json.dumps({"ask": "ASK-nope",
                                             "decision": "approve"}).encode())
    assert s == 404 and b"not an open ask" in p


def test_only_the_decide_verb_answers_post():
    assert front_door.handle("/front/rows", {}, "POST", b"{}") is None
    assert front_door.handle("/front/decide", {}, "GET", b"") is None, (
        "the write verb never answers a GET")


# --------------------------------------------------------------------------- the talk path


def test_seat_notice_preserves_queued_status_unknown_and_send_unknown(monkeypatch):
    from laplace.representation import atlas_bridge

    def send(**kwargs):
        seat = kwargs["recipient_seat_id"]
        if seat == "claude-seat":
            return {
                "message_id": "message:claude",
                "receipt": {"event_id": "event:claude"},
                "status": None,
                "status_observation": {
                    "state": "unknown-after-append",
                    "error": {"type": "RuntimeError", "message": "readback failed"},
                    "append_proof": "event:claude",
                },
            }
        if seat == "ego-seat":
            raise TimeoutError("planted lock timeout")
        return {
            "message_id": "message:codex",
            "receipt": {"event_id": "event:codex"},
            "status": {"status": "queued"},
            "status_observation": {
                "state": "known", "error": None, "append_proof": "event:codex",
            },
        }

    monkeypatch.setattr(atlas_bridge, "send", send)

    routing = front_door._tell_the_seats(
        "a routing attack",
        {"id": "TALK-ATTACK", "text": "preserve unknown"},
        "the send outcomes must remain typed",
        audience=["codex-seat", "claude-seat", "ego-seat", "interface-seat"],
    )

    assert routing["told"] == ["codex-seat", "claude-seat"]
    assert routing["unknown"] == ["ego-seat"]
    # /2 DROPPED `unreached`, and this test must assert the DROP rather than the value.
    # Under /1 it was the literal [] on every path and got banked into every talk-routed
    # row, so a fold computed "0 unreached" and read full delivery — reassurance
    # manufactured from a field that could never be non-empty. Nothing here proves a seat
    # was NOT reached, and FIND-20260825-unreached-can-name-a-reached-seat proves a list
    # of that name can be wrong in the other direction too.
    assert "unreached" not in routing, (
        "a field that can never be non-empty must not exist; its absence is the cure")
    assert routing["schema_version"].endswith("/2"), (
        "the version must move, so a fold can tell the two shapes apart instead of "
        "reading a missing key as an empty one")
    by_seat = {outcome["seat_id"]: outcome for outcome in routing["outcomes"]}
    assert by_seat["codex-seat"]["state"] == "queued"
    assert by_seat["claude-seat"]["state"] == "queued-status-unknown"
    assert by_seat["claude-seat"]["send_event_id"] == "event:claude"
    assert by_seat["ego-seat"]["state"] == "unknown"
    assert by_seat["ego-seat"]["error"]["type"] == "TimeoutError"


def test_the_talk_door_banks_before_any_travel_and_threads_receipts(tmp_path, monkeypatch):
    (tmp_path / "contract").mkdir()
    monkeypatch.setattr(front_door, "_repo_root", lambda: tmp_path)
    monkeypatch.setitem(sources.SOURCES["talk"], "path",
                        str(tmp_path / "contract" / "talk.jsonl"))
    monkeypatch.setattr(
        front_door,
        "_prepare_talk_audience",
        lambda requested: ("eigen", ("codex-seat", "claude-seat"), None),
    )
    s, _c, p = front_door.handle("/front/talk", {}, "POST",
                                 json.dumps({"text": "how goes the organ?"}).encode())
    assert s == 202
    tid = json.loads(p)["banked"]
    store = tmp_path / "contract" / "talk.jsonl"
    rows_now = [json.loads(line) for line in store.read_text().splitlines()]
    talk = [r for r in rows_now if r.get("record") == "talk"][0]
    assert talk["actor"] == "gerard" and talk["to"] == "eigen" and talk["id"] == tid
    assert talk["recipient_seat_ids"] == ["codex-seat", "claude-seat"]
    # THE CONTRACT CHANGED AND THIS TEST WAS HOLDING THE OLD ONE IN PLACE. It asserted
    # routed_count 0 with a "banked-for-broker" residual — i.e. it encoded "his message
    # reaches nobody" AS THE LAW, deferring to a broker that does not exist. His words
    # bank first (unchanged, and the point of this test), then route over the fabric
    # every seat already watches, and whatever fails to route is NAMED.
    # DELIVERY IS A SEPARATE FACT AND STAYS ONE. The old contract asserted routed_count
    # 0 with a "banked-for-broker" residual — it encoded "his message reaches nobody" as
    # the law. The new contract cannot honestly assert a count either: one fabric send
    # costs ~53s (it replays the store), so routing runs off the request path and the
    # OUTCOME banks as a talk-routed row. What the response owes him is the truth about
    # what it has and has not yet done.
    payload = json.loads(p)
    assert payload["intended_count"] >= 1
    assert payload["routed_count"] is None, (
        "a count claimed before the sends complete would be a delivery claim in advance")
    assert payload["routing_complete"] is False
    residual = payload["routing_residual"][-1]
    assert residual["state"] == "dispatching"
    assert residual["to"], "the seats being notified must be NAMED, never implied"
    # a reply row flips the thread state, computed from rows at render
    with open(store, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"record": "talk-reply", "target": tid,
                             "actor": "ego", "text": "green at 65",
                             "ts": "2026-08-24T13:00:00Z"}) + "\n")
    assert "green at 65" in front_door._frag_talk()


def test_the_talk_door_binds_from_the_complete_materialization_frontier(
    tmp_path, monkeypatch
):
    from laplace.representation import atlas_bridge
    from tests.test_conversation_serve import _blueprint

    (tmp_path / "contract").mkdir()
    monkeypatch.setattr(front_door, "_repo_root", lambda: tmp_path)
    monkeypatch.setitem(
        sources.SOURCES["talk"], "path", str(tmp_path / "contract" / "talk.jsonl")
    )
    monkeypatch.setattr(
        front_door,
        "_prepare_talk_audience",
        lambda requested: ("eigen", ("codex-seat", "claude-seat"), None),
    )
    calls = []

    def projection(**kwargs):
        calls.append(kwargs)
        return _blueprint()

    monkeypatch.setattr(atlas_bridge, "blueprint_projection", projection)
    status, _ctype, _payload = front_door.handle(
        "/front/talk",
        {},
        "POST",
        json.dumps({"text": "unify the interface and attention broker"}).encode(),
    )

    assert status == 202
    assert calls == [{"materialization_limit": None, "result_limit": 1}]
    talk = json.loads((tmp_path / "contract" / "talk.jsonl").read_text().splitlines()[0])
    assert talk["blueprint_materialization_ids"] == ["sha256:" + "c" * 64]
    assert talk["blueprint_route_binding"]["omitted_count"] == 0


def test_exact_source_door_refuses_an_entire_stale_blueprint_generation(
    tmp_path, monkeypatch
):
    from laplace.representation import atlas_bridge

    source = tmp_path / "design.md"
    content = b"the exact clause is unchanged"
    source.write_bytes(content)
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    projection = {
        "generation_id": "sha256:" + "a" * 64,
        "current": False,
        "moved_source_roots": [{
            "path": "other.md",
            "expected": "sha256:" + "b" * 64,
            "actual": "sha256:" + "c" * 64,
        }],
        "source_roots": {"design.md": digest, "other.md": "sha256:" + "b" * 64},
    }
    monkeypatch.setattr(front_door, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(atlas_bridge, "blueprint_projection", lambda **_kwargs: projection)
    query = {
        "path": ["design.md"],
        "start": ["0"],
        "end": [str(len(content))],
        "expect": [digest],
        "format": ["json"],
    }

    status, _ctype, payload = front_door.handle(
        "/front/serve/source", query, "GET", b""
    )

    assert status == 409
    assert b"stale blueprint frontier moved" in payload

    projection["current"] = True
    projection["moved_source_roots"] = []
    status, _ctype, payload = front_door.handle(
        "/front/serve/source", query, "GET", b""
    )
    assert status == 200
    assert json.loads(payload)["content"] == content.decode()


def test_the_talk_door_refuses_junk(tmp_path, monkeypatch):
    monkeypatch.setattr(front_door, "_repo_root", lambda: tmp_path)
    s, _c, p = front_door.handle("/front/talk", {}, "POST", b"[]")
    assert s == 400
    s, _c, p = front_door.handle("/front/talk", {}, "POST",
                                 json.dumps({"text": "   "}).encode())
    assert s == 400 and b"empty" in p
    s, _c, p = front_door.handle("/front/talk", {}, "POST",
                                 json.dumps({"text": "x" * 8001}).encode())
    assert s == 400 and b"8000" in p
    assert front_door.handle("/front/talk", {}, "GET", b"") is None


def test_conversation_read_faces_share_exact_custody_adapter_without_self_healing(
    monkeypatch,
):
    from laplace.representation import atlas_bridge
    from laplace.web.conversation_serve import canonical_bytes, turn_handle
    from tests.test_conversation_serve import _blueprint, _state, _turn

    turn = _turn()
    exact = canonical_bytes({
        "schema_version": "laplace.author-turn/1",
        "row": turn,
    })
    custody_reads = []

    monkeypatch.setattr(
        rows,
        "scan",
        lambda source: iter(((0, turn),)) if source == "talk" else iter(()),
    )
    monkeypatch.setattr(atlas_bridge, "snapshot", lambda: {"provider": _state(turn)})
    monkeypatch.setattr(
        atlas_bridge,
        "blueprint_projection",
        lambda **_kwargs: _blueprint(),
    )

    def custody_body(*, handle):
        custody_reads.append(handle)
        return {
            "content_handle": handle,
            "text": exact.decode("utf-8"),
            "base64": None,
            "bytes": len(exact),
        }

    def refuse_write(_data):
        raise AssertionError("GET attempted to self-heal custody")

    monkeypatch.setattr(atlas_bridge, "custody_body", custody_body)
    monkeypatch.setattr(atlas_bridge, "put_custody", refuse_write)

    serve_status, _ctype, serve_body = front_door.handle(
        "/front/serve", {"format": ["json"]}, "GET", b""
    )
    talk_status, _ctype, _talk_body = front_door.handle(
        "/front/talkpane", {}, "GET", b""
    )

    assert serve_status == talk_status == 200
    assert json.loads(serve_body)["author_turn_custody"]["status"] == "CUSTODY_EXACT"
    assert custody_reads == [turn_handle(turn), turn_handle(turn)]


def test_conversation_read_adapter_keeps_missing_custody_readable(monkeypatch):
    from laplace.representation import atlas_bridge
    from tests.test_conversation_serve import _blueprint, _state, _turn

    turn = _turn()

    def missing(*, handle):
        raise atlas_bridge.BlobMissing("planted absent custody", key=handle)

    monkeypatch.setattr(atlas_bridge, "custody_body", missing)
    serve = front_door._conversation_serve_projection(
        turn, _state(turn), _blueprint()
    )

    assert serve["read_only"] is True
    assert serve["author_turn_custody"]["status"] == "CUSTODY_ABSENT"
    assert serve["acknowledgement_eligible"] is False
    assert any(
        row["class"] == "author-turn-custody-absent"
        for row in serve["omission_residual"]
    )


def test_conversation_author_face_hides_transport_vocabulary(monkeypatch):
    from laplace.web.conversation_serve import materialize_conversation_serve
    from tests.test_conversation_serve import _blueprint, _state, _turn

    turn = _turn()
    serve = materialize_conversation_serve(turn, _state(turn), _blueprint())
    html = front_door._frag_conversation_serve(serve)
    assert "queued" not in html and "pulled" not in html

    monkeypatch.setattr(front_door, "_conversation_serve_data", lambda _talk_id="": serve)
    status, _ctype, body = front_door._conversation_serve_get({"format": ["json"]})
    payload = json.loads(body)
    assert status == 200
    assert "browser_event_cursor" not in payload and "dependency_frontier" not in payload
    assert all("transport_state" not in row for row in payload["recipient_states"])
    assert "queued" not in body.decode("utf-8") and "pulled" not in body.decode("utf-8")


def test_conversation_ground_key_fault_is_not_misreported_as_absent(monkeypatch):
    def broken(_talk_id=""):
        raise KeyError("active_context")

    monkeypatch.setattr(front_door, "_conversation_serve_data", broken)
    status, _ctype, body = front_door._conversation_serve_get({})
    assert status == 503
    assert b"KeyError" in body and b"active_context" in body


# --------------------------------------------------------------------------- the walk door

def test_the_walk_door_banks_his_accept_with_the_gates_own_substring(tmp_path, monkeypatch):
    (tmp_path / "corpus_friction").mkdir()
    (tmp_path / "contract").mkdir()
    store = tmp_path / "corpus_friction" / "work_orders.jsonl"
    store.write_text("", encoding="utf-8")
    monkeypatch.setattr(front_door, "_repo_root", lambda: tmp_path)
    monkeypatch.setitem(sources.SOURCES["work_orders"], "path", str(store))
    s, _c, p = front_door.handle("/front/walked", {}, "POST",
                                 json.dumps({"stage": "m1", "verdict": "accept",
                                             "text": "the board reads right"}).encode())
    assert s == 200
    banked = json.loads(p)["banked"]
    assert "front-door-m1-walked" in banked, (
        "the accept row's id must carry the exact substring CAMP-R3's gate greps")
    row = [json.loads(line) for line in store.read_text().splitlines()
           if '"walk-verdict"' in line][0]
    assert row["actor"] == "gerard" and row["verdict"] == "accepted"
    # the strip renders M1 accepted, computed from the row — face first ("your
    # acceptance, banked <date>"), the row id in the machine register (title/href)
    strip = front_door._frag_walkstrip()
    assert "approved" in strip and "your approval, recorded" in strip
    assert banked in strip, "the id must stay summonable — title and href, never lost"


def test_the_walk_door_refuses_wordless_redlines_and_unbuilt_stages(tmp_path, monkeypatch):
    monkeypatch.setattr(front_door, "_repo_root", lambda: tmp_path)
    s, _c, p = front_door.handle("/front/walked", {}, "POST",
                                 json.dumps({"stage": "m1", "verdict": "redline",
                                             "text": ""}).encode())
    assert s == 400 and b"cures nothing" in p
    s, _c, p = front_door.handle("/front/walked", {}, "POST",
                                 json.dumps({"stage": "m4", "verdict": "accept"}).encode())
    assert s == 400 and b"only built stages walk" in p
    # a redline banks WITHOUT the gate substring — the gate flips only on his yes
    (tmp_path / "corpus_friction").mkdir()
    (tmp_path / "contract").mkdir()
    store = tmp_path / "corpus_friction" / "work_orders.jsonl"
    store.write_text("", encoding="utf-8")
    monkeypatch.setitem(sources.SOURCES["work_orders"], "path", str(store))
    s, _c, p = front_door.handle("/front/walked", {}, "POST",
                                 json.dumps({"stage": "m2", "verdict": "redline",
                                             "text": "the composer is cramped"}).encode())
    assert s == 200
    assert "front-door-m2-walked" not in json.loads(p)["banked"]


# ------------------------------------------------------- silence vs death (2026-08-25)

def test_a_quiet_event_ledger_is_not_a_concern():
    """His steer, standing at the brief: "I see seats is red but know neither what that
    means or what I'm supposed to do about it. Indeed, what I _can_ do about it."

    contract/seats.jsonl is a FOUNDING ledger — it appends when a seat is founded, and its
    last rows are "superego live" / "interface live". Given a 24h wall-clock budget it went
    red 24h after the last founding, and the brief reported "1 NEEDS YOU · gone quiet 24h ·
    worst seats" while the live fabric was at cursor 630 and the busiest organ in the
    engine. A false alarm on his attention that he could not have discharged if he tried.
    """
    from laplace.engine import sources

    st = sources.stat("seats")
    assert st["expectation"] == "ledger"
    assert st["quiet_is_normal"] is True
    # `red` keeps its old meaning for surfaces that read it; `concern` is the only thing
    # allowed to spend his attention.
    assert st["concern"] is False, "a quiet founding ledger must never be a concern"


def test_every_source_declares_what_its_silence_means():
    """A store with no declared expectation defaults to feed, which means any new store
    that is really a ledger will start crying for his attention the moment it settles.
    Assert the field exists on every row so the choice is always made, never inherited."""
    from laplace.engine import sources

    for row in sources.roster():
        if row.get("absent"):
            continue
        assert row.get("expectation") in ("feed", "ledger"), row.get("name")


def test_a_stale_feed_tells_him_what_would_clear_it_and_whose_hand():
    """Every anchor in the NEEDS YOU zone must name the act that ends it. An entry that
    names a state without naming its discharge is a demand with no way to answer it —
    which is what sent him to the engine room to look at a red he could do nothing about.
    """
    from laplace.engine import sources

    real = sources.stat

    def dying_feed(name):
        row = real(name)
        if name == "journal":                      # a genuine feed, forced past budget
            row = dict(row, age_s=999999.0, red=True, concern=True, expectation="feed")
        return row

    sources.stat = dying_feed
    try:
        _status, _ctype, body = front_door.handle("/front/apex", {}, "GET", b"")
        html = body.decode("utf-8")
    finally:
        sources.stat = real

    assert "gone quiet" in html, "a dead feed must still reach the needs zone"
    assert 'class="clears"' in html, (
        "the anchor names a state but not the act that ends it — the exact defect he hit")
    assert "a seat clears this, not you" in html, (
        "a store only a seat can write must say so; otherwise he is left holding it")

    # AND IT MUST NOT BE IN HIS COUNT. Saying "not yours" while counting it as his was
    # the defect this test's own cure created: the badge read `1 NEEDS YOU` over a card
    # whose body said he could do nothing about it (his steer, 2026-08-25: "complaining
    # about ages on stores and yet tells me it needs me but that I don't need to do
    # anything"). The prose was necessary and was never sufficient — the partition is.
    assert "the engine owes itself 1" in html, (
        "a seat-cleared item belongs under its own heading, not his")
    assert "nothing needs you right now" in html, (
        "with only seat-owed items outstanding the strip must NOT claim he is needed")
    assert '<div class="bignum ok">0</div>' in html, (
        "the big number over `needs you` counts only what HIS hand can discharge")
    assert 'class="anchors quiet"' in html, "the seat-owed list renders demoted, not hidden"


def test_the_door_census_is_itself_a_door():
    """It certifies every other surface and was in no nav, no keymap and no route — the
    router's old hand-typed no-route message had to apologise for exactly this class."""
    from laplace.web import front_places

    hrefs = {p["href"] for p in front_places.census()["places"]}
    assert "/front/selftest" in hrefs


def test_standalone_doors_are_documents_not_fragments():
    """A door the shell never fetches is a PAGE. Served as a bare fragment it had no
    doctype, no title and a transparent body — measured rendering as 16px black Times
    New Roman on WHITE, in a dark-only instrument, on the page whose job is to certify
    that the others work."""
    status, ctype, body = front_door.handle("/front/selftest", {}, "GET", b"")
    html = body.decode("utf-8")
    assert status == 200 and ctype.startswith("text/html")
    assert html.startswith("<!doctype html>"), "no doctype — the browser renders quirks mode"
    assert "<title>" in html and "color-scheme:dark" in html
    assert 'href="/front"' in html, "a standalone page must carry a way back"


def test_a_door_that_needs_a_parameter_is_not_reported_as_down():
    """/front/serve answers 404 when fired bare — {"error": "author turn '' is absent"} —
    which is the door refusing to guess, not the door failing. The census flagged it RED,
    so the one instrument whose job is to prove the surface is honest carried a permanent
    false alarm. Same category error as judging a founding ledger against a freshness
    budget: a refusal to guess is not death."""
    from laplace.web import front_places

    # The INVARIANT, not one door's spelling. /front/serve was the motivating case and
    # codex has since cured it to answer 200 bare, so the exemption is now unused — a
    # good outcome, and the reason this asserts the rule rather than the example.
    html = front_door.handle("/front/selftest", {}, "GET", b"")[2].decode("utf-8")
    for door in front_door._PARAMETERISED_DOORS:
        status = (front_door.handle(door, {}, "GET", b"") or (500,))[0]
        if status in (400, 404):
            assert "want of a parameter" in html, (
                f"{door} refuses for want of an argument and the census does not say so")

    # THE INVARIANT, held against the FIRE rather than the chip. The chip is no longer a
    # fire: _census_selftest renders the last banked run because firing all twelve doors
    # cost 16,971ms of an 18,879ms /front/places — his BOOT path (his steer, 2026-08-25,
    # "hilariously inefficient chrome"). And _bank_selftest refuses to write from a test
    # at all, so a fixture's failure can never reach his nav
    # (FIND-20260825-test-suite-forges-production-receipts, whose cure this nearly undid).
    # So the rule is asserted where it actually lives: the rendered census.
    for door in front_door._PARAMETERISED_DOORS:
        status = (front_door.handle(door, {}, "GET", b"") or (500,))[0]
        if status in (400, 404):
            row = html[html.index(door):html.index(door) + 400]
            assert 'class="red"' not in row.split("</tr>")[0], (
                f"{door} refuses for want of an argument and is rendered as a FAILING "
                f"door — a permanent false alarm on the one instrument that certifies "
                f"the surface")

    census = {p["id"]: p for p in front_places.census()["places"]}
    src = census["selftest"]["source"]
    assert "fires no door" in src or "has not run" in src, (
        "the nav chip must state that it is a render of a banked run, never a live fire")


def test_selftest_bank_refuses_the_process_lifetime_test_sentinel(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(front_door, "_repo_root", lambda: tmp_path)
    monkeypatch.setenv("LAPLACE_TEST_PROCESS", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    front_door._bank_selftest(12, 0, [])

    assert not (tmp_path / front_door._SELFTEST_BANK).exists()


def test_only_built_stages_accept_a_verdict_even_though_the_gate_names_more():
    """THE GUARD THAT WAS MISSING WHEN A FORGED ROW GOT BANKED.

    The CAMP-R3 gate greps m1..m4; only m1..m2 are built. Widening the accept path to
    the gate's set removed this refusal, and a diagnostic call then banked
    RES-20260825T114838-front-door-m4-walked with actor="gerard" for a milestone no
    built surface stands behind (retracted:
    RETRACT-20260825-front-door-m4-walked-not-his).

    The gate names the PROGRAMME. This names what his hand may rule on today. They are
    different sets and must never be collapsed again.
    """
    assert set(front_door._WALKABLE) < set(front_door._walkable()), (
        "the built set must be a strict subset of the gate's programme set")
    for stage in front_door._walkable():
        if stage in front_door._WALKABLE:
            continue
        status, _c, payload = front_door.handle(
            "/front/walked", {}, "POST",
            json.dumps({"stage": stage, "verdict": "accept"}).encode())
        assert status == 400, f"{stage} is not built and must be refused, got {status}"
        assert b"only built stages walk" in payload


def test_an_unbuilt_milestone_is_shown_but_never_offered():
    """He should see why the gate will not flip, without being handed a button the door
    would refuse. A control that cannot work is a lie told in the most convincing place."""
    html = front_door._frag_walkstrip()
    for stage in front_door._walkable():
        assert stage.upper() in html, f"{stage} is invisible — the gate's set must be shown"
    assert "not built" in html
    offered = re.findall(r'data-walk="(m\d+)"', html)
    assert set(offered) <= set(front_door._WALKABLE), (
        f"a verdict button was offered for an unbuilt stage: {offered}")


def test_the_walk_strip_leads_with_faces_not_tokens():
    """His three laws, asserted where they were hammered: zero-context (the default
    register is readable with no session history), conjugate handles (faces lead; ids
    are summonable, never leading), plain technical English (the copy is the minting
    row's own words). The strip once offered an irreversible ruling on the bare token
    "M1"; his verdict, verbatim: "what am I meant to do with that?"
    """
    html = front_door._frag_walkstrip()

    # faces derived from the programme note lead the default register
    assert "the read surface" in html
    assert "the talk path" in html
    # the gloss is authored vocabulary, grounded in the programme note — the audit
    # measured verbatim quotation failing all three laws at once
    assert "saved as a row" in html

    # the DEFAULT register — the TEXT a reader sees outside the mechanics folds —
    # carries no ids. Attributes (href, title) are the machine register and exempt:
    # they are summonable, not visible.
    visible = re.sub(r"<details.*?</details>", "", html, flags=re.S)
    visible_text = re.sub(r"<[^>]+>", " ", visible)
    bare = re.findall(r"\b(?:RES|VERDICT|NOTE|WO|WALKRED|CAMP)-[A-Za-z0-9-]+",
                      visible_text)
    assert not bare, f"internal handles leaked into the default register: {bare}"

    # the machine register still exists — summonable, inside the folds
    assert "CAMP-R3" in html and "front-door-" in html


def test_a_retracted_acceptance_never_renders_as_walked():
    """The scan once counted the RETRACTION of the forged m4 row as the walk itself —
    the retraction's own id contains "front-door-m4-walked", and the closure test was a
    substring grep. Typed closure now: a walk is a row that SAYS record=walk-verdict,
    verdict=accepted, stage=front-door-<s>. The retraction hazard this guards is real
    and banked: RETRACT-20260825-front-door-m4-walked-not-his."""
    state = front_door._walk_scan()["state"]
    m4 = state.get("m4", {})
    assert not m4.get("walked"), "a retracted acceptance is rendering as his walk"
    assert m4.get("retracted"), "the retraction disappeared from the scan entirely"


# --- the suite may not write to the live fabric ----------------------------
# Three author-act events — cursors 929/960/961, all interface-seat -> ego-seat — were
# appended to the AUTHORITATIVE Atlas ledger by pytest, citing WALKRED rows that exist
# nowhere and carrying body handles that do not resolve. They reconstruct byte-exactly
# from the literal "the composer is cramped" in
# test_the_walk_door_refuses_wordless_redlines_and_unbuilt_stages, above. Events asserting
# THE AUTHOR ACTED were being forged into the authority, once per suite run.
# MECHANISM: /front/walked dispatches its notice on a DAEMON THREAD; by the time it runs,
# monkeypatch is torn down, so the blob put resolves LAPLACE_STATE fresh into a dead tmp
# dir while the append reaches the live store through an lru_cached handle.
# This was the THIRD attempt at this class (6be772d5 for the receipt bank, the selftest
# bank guard, now this) and the first one placed at the write door rather than at a caller.

def test_a_test_process_cannot_write_to_the_live_atlas_fabric():
    """THE COUNTEREXAMPLE, planted: under pytest the live root must be refused, and only
    the live root — a test that legitimately drives a tmp store must still work."""
    from laplace.representation import atlas_bridge as ab

    with pytest.raises(ab.LiveStoreUnderTest):
        ab._refuse_live_write_under_test(ab._LIVE_ROOT)

    ab._refuse_live_write_under_test(Path("/tmp/pytest-of-nobody/atlas/conceptric"))
    ab._refuse_live_write_under_test(Path("/tmp/pytest-of-nobody/other"))


def test_the_gate_does_not_fire_outside_a_test_process(monkeypatch):
    """It must key on the TEST PROCESS, never on the path. A gate that also blocked the
    engine writing to its own store would take the fabric down to protect it."""
    from laplace.representation import atlas_bridge as ab

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("LAPLACE_TEST_PROCESS", raising=False)
    ab._refuse_live_write_under_test(ab._LIVE_ROOT)


def test_a_send_never_queues_a_body_its_own_custody_cannot_resolve(monkeypatch):
    """CONTENT BEFORE COMMITMENT. custody_has has existed since atlas_bridge was written
    and was never called on the send path, so a put landing in one store and an append
    reaching another produced a queued handle nothing could resolve — the exact shape of
    the three forged events. Planted by making the put land somewhere the check cannot see."""
    from laplace.representation import atlas_bridge as ab

    class _Elsewhere:
        def __init__(self, root):
            self.root = root

        def put(self, data: bytes) -> str:
            return "sha256:" + "0" * 64          # a handle that was never banked here

        def get(self, handle: str) -> bytes:
            raise ab.BlobMissing("planted missing body", key=handle)

    monkeypatch.setattr(ab, "BlobStore", _Elsewhere)
    with pytest.raises(ab.StateTransitionRefused) as caught:
        ab.send(sender_seat_id="interface-seat", recipient_seat_id="ego-seat",
                message_type="author-act", body="the composer is cramped",
                dependency_roots={}, idempotency_key="planted", expires_at="2026-09-01T00:00:00Z",
                provider="test", model="test")
    assert "did not land in the custody" in str(caught.value)


def test_every_place_is_censused():
    """THE DIRECTION THAT WAS NEVER CHECKED, and it is how the drift happened.

    front_places' own docstring claimed "a route cannot exist without a census row, and a
    census row cannot name a route that is not served — tests assert BOTH directions." Only
    the easy direction was ever asserted: that every census row answers. Nothing checked
    that a route he can REACH is covered by the door census. So /front/conceptric shipped as
    a route and a nav place, stayed out of _SELFTEST_DOORS, and the QA chip rendered
    "12 doors · 0 not answering" over a pane that was raising TypeError on every seat.

    A green QA surface over an uncertified door is absence rendered as reassurance — the
    law front_places states in prose two hundred lines from where it breaks it.
    """
    from laplace.web import front_places

    # THE ONE LAWFUL EXEMPTION, named rather than the assertion weakened: the census
    # fires every door in-process, so censusing itself is unbounded recursion. Any other
    # absence is drift.
    EXEMPT = {"/front/selftest"}

    served = {str(p["href"]).split("?")[0] for p in front_places.census()["places"]
              if str(p.get("href", "")).startswith("/front/")}
    missing = sorted(served - set(front_door._SELFTEST_DOORS) - EXEMPT)
    assert not missing, (
        "every /front place he can reach from the nav must be in the door census; "
        f"uncensused: {missing}")


def test_a_door_that_needs_an_id_refuses_an_empty_one(monkeypatch):
    """An empty id fell through to the FIRST ROW IN THE STORE and returned a real,
    plausible, wrong record. A bogus id already refused correctly; only empty slipped —
    the same shape as a blank seat term compiling to a regex that matches everything,
    which account_seat was hardened against for exactly this reason."""
    for door in ("/front/conceptric/seat", "/front/conceptric/event"):
        status, _c, body = front_door.handle(door, {"id": [""]}, "GET", b"")
        assert status == 400, f"{door} resolved an empty id instead of refusing"
        assert b"caller error" in body


def test_the_append_capability_refuses_any_root_a_test_does_not_own():
    """CODEX'S PLANT, kept. My first cure guarded laplace.representation.atlas_bridge._store() against a
    COMPILED DEFAULT root and I called it a universal write door. It was neither: a direct
    ConceptricStore(root).append() bypassed the helper, and

        LAPLACE_TEST_PROCESS=1 LAPLACE_STATE=/tmp/laplace-production-alt

    was ALLOWED, because the configured live root was not the constant being guarded.
    A denylist has to predict every production path; an allowlist only has to recognise a
    test one — so the rule inverted, and moved to append_many, which append delegates to.

    My SECOND attempt then admitted the world: it allowed any path component starting
    "tmp", and /tmp starts with tmp. Both counterexamples are held here."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from atlas.store import LiveStoreUnderTest, _refuse_test_write

    for allowed in ("/tmp/pytest-of-someone/pytest-3/test_x0/atlas/conceptric",
                    "/tmp/tmpabc123xy/atlas/conceptric"):
        _refuse_test_write(Path(allowed))          # a test's own root still writes

    for refused in (str(Path.home() / ".mcp-gerard/laplace/atlas/conceptric"),
                    "/tmp/laplace-production-alt/atlas/conceptric",   # codex's plant
                    "/tmp/atlas/conceptric",                          # bare /tmp
                    "/var/lib/laplace/atlas/conceptric"):
        with pytest.raises(LiveStoreUnderTest):
            _refuse_test_write(Path(refused))


def test_a_causal_cycle_gets_no_depth_and_the_answer_does_not_depend_on_order():
    """CODEX'S SECOND PLANT. I called an iterative traversal "cycle-safe" because it could
    not recurse the page down. That is not safety: on A<->B, visiting (A,B) yielded
    {B:0, A:1} and (B,A) yielded {A:0, B:1} — one graph, two answers, neither a distance
    from a root, BECAUSE A CYCLE HAS NO ROOT. My own test asserted only that the output
    was total and non-negative, which blessed the invention.

    Depth is now computed over the SCC condensation; cycle members get no depth at all and
    are counted in a residual."""
    from laplace.engine import descent_telemetry

    class _E:
        def __init__(self, i, c):
            self.event_id, self.causation_ids = i, c

    ab, res_ab = descent_telemetry._depths([_E("A", ("B",)), _E("B", ("A",))])
    ba, res_ba = descent_telemetry._depths([_E("B", ("A",)), _E("A", ("B",))])
    assert ab == ba == {}, "a cycle member must get NO depth, in either visit order"
    assert res_ab["cyclic_events"] == res_ba["cyclic_events"] == 2
    assert res_ab["cycles"] == 1

    # and an ordinary chain still depths correctly
    chain, res = descent_telemetry._depths(
        [_E("r", ()), _E("m", ("r",)), _E("t", ("m",))])
    assert chain == {"r": 0, "m": 1, "t": 2}
    assert res["cyclic_events"] == 0
