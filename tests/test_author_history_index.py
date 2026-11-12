"""The history projection is derived once and reused while its sources stand still.

The page is bounded (``MAX_LIMIT = 20``, clamped on every call) while the projection it
pages was rebuilt per call: 266 calls to walk the author's own record, 238 ms each,
63.3 s (harness2/baseline/storage.json ``storage.history.real_ledger.paged``).  These
tests fix the three properties the derived index has to have: it is keyed by what the
filesystem says about the files the fold reads, it names EVERY such file (observed, not
assumed), and what it hands out cannot be changed by a caller that holds a page.
"""
from __future__ import annotations
from laplace.writing import records as record_owner

import builtins
import json
import os
from pathlib import Path

from laplace.work import history as author_history


def _fixture(root: Path) -> None:
    manuscript = root / "sources" / "book"
    (manuscript / "feedback").mkdir(parents=True)
    (manuscript / "main.tex").write_text("Old prose.\n", encoding="utf-8")
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "book", "kind": "tex", "project_dir": "sources/book",
        "manuscript_dir": "sources/book", "tex_root": "sources/book",
        "versions_dir": "sources/book/versions",
        "document": {"root": "main.tex", "manuscript_dir": "sources/book"}}]}),
        encoding="utf-8")
    (manuscript / "authoring.json").write_text(json.dumps({
        "schema_version": "laplace.authoring/1", "project": "book", "revision": 1,
        "argument_revision": 0, "argument": "", "framing": {}, "section_ids": [],
        "contexts": [], "corrections": [{
            "id": "AC-one", "project": "book", "created": "2026-09-30T10:00:00Z",
            "text": "Retain the qualification.", "kind": "factual", "scope": "passage",
            "anchor": {"file": "main.tex", "line_start": 1, "line_end": 1},
            "by": "author", "status": "open"}]}), encoding="utf-8")
    (manuscript / "feedback" / "feedback.jsonl").write_text("", encoding="utf-8")
    (root / "contract").mkdir(parents=True)
    rows = [
        {"record": "writing-session", "id": "WS-one", "project": "book",
         "provider": "codex", "role": "author", "ts": "2026-09-30T10:01:00Z"},
        {"record": "writing-turn", "id": "WT-one", "session_id": "WS-one",
         "project": "book", "text": "Revise.", "ts": "2026-09-30T10:02:00Z"},
    ]
    (root / "contract" / "talk.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _clear() -> None:
    author_history._ALL_CACHE.clear()
    author_history._TALK_CACHE.clear()


def test_every_file_the_fold_opens_is_a_file_the_index_stamps(tmp_path: Path) -> None:
    """Observed, not assumed: if an adapter grows a source, this fails here.

    The same observation as
    evidence/WRITING_CONSOLIDATION_2026-10-03/wave1/storage-latency/probes/
    history_sources.py, run as a test so the declaration cannot silently fall behind.
    """
    _fixture(tmp_path)
    _clear()
    author_history.history("book", {}, repo_root=tmp_path)      # warm the talk index
    seen: list[Path] = []
    real_open, real_text, real_bytes = builtins.open, Path.read_text, Path.read_bytes

    def note(value) -> None:
        try:
            seen.append(Path(value).resolve())
        except (TypeError, ValueError, OSError):
            pass

    builtins.open = lambda file, *a, **k: (note(file), real_open(file, *a, **k))[1]
    Path.read_text = lambda self, *a, **k: (note(self), real_text(self, *a, **k))[1]
    Path.read_bytes = lambda self, *a, **k: (note(self), real_bytes(self, *a, **k))[1]
    try:
        author_history._fold("book", tmp_path)
    finally:
        builtins.open, Path.read_text, Path.read_bytes = real_open, real_text, real_bytes

    files, directories = author_history._source_paths("book", tmp_path)
    stamped = {path.resolve() for path in files}
    inside = [path for path in seen
              if str(path).startswith(str(tmp_path.resolve()))]
    assert inside, "the fold read nothing inside the fixture"
    for path in inside:
        if path in stamped:
            continue
        assert any(directory.resolve() in path.parents for directory in directories), (
            f"{path} is read by the fold and stamped by neither a declared file nor a "
            f"declared directory; add it to author_history._source_paths")


def test_a_second_page_is_served_from_the_index_and_an_appended_row_rebuilds_it(
        tmp_path: Path) -> None:
    _fixture(tmp_path)
    _clear()
    folds = []
    real_fold = author_history._fold
    author_history._fold = lambda *a, **k: (folds.append(1), real_fold(*a, **k))[1]
    try:
        first = author_history.history("book", {}, repo_root=tmp_path)
        assert len(folds) == 1
        author_history.history("book", {"offset": 0, "as_of": first["as_of"]},
                               repo_root=tmp_path)
        author_history.history("book", {"offset": 0, "as_of": first["as_of"]},
                               repo_root=tmp_path)
        assert len(folds) == 1, "a page is a slice of the derived index, not a refold"

        with (tmp_path / "contract" / "talk.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"record": "writing-turn", "id": "WT-two",
                                 "session_id": "WS-one", "project": "book",
                                 "text": "Again.", "ts": "2026-09-30T11:00:00Z"}) + "\n")
        again = author_history.history("book", {}, repo_root=tmp_path)
        assert len(folds) == 2, "an appended ledger row must rebuild the projection"
        assert again["pagination"]["total"] > first["pagination"]["total"]

        # A source that is not the ledger counts too.
        state = json.loads((tmp_path / "sources/book/authoring.json").read_text())
        state["corrections"].append({
            "id": "AC-two", "project": "book", "created": "2026-09-30T12:00:00Z",
            "text": "And this one.", "kind": "style", "scope": "project",
            "anchor": {}, "by": "author", "status": "open"})
        (tmp_path / "sources/book/authoring.json").write_text(json.dumps(state),
                                                              encoding="utf-8")
        third = author_history.history("book", {}, repo_root=tmp_path)
        assert len(folds) == 3
        assert third["pagination"]["total"] > again["pagination"]["total"]
    finally:
        author_history._fold = real_fold


def test_unrelated_reply_bodies_are_not_retained_or_refolded(tmp_path: Path) -> None:
    _fixture(tmp_path)
    talk = tmp_path / "contract" / "talk.jsonl"
    with talk.open("a", encoding="utf-8") as stream:
        for index in range(200):
            stream.write(json.dumps({"record": "writing-reply", "id": f"other-{index}",
                                     "project": "unrelated", "text": "x" * 1024,
                                     "ts": "2026-09-30T10:03:00Z"}) + "\n")
    _clear()
    first = author_history.history("book", {}, repo_root=tmp_path)
    state = author_history._TALK_CACHE[(str(tmp_path.resolve()), "book")]
    assert {row["id"] for row in state["rows"]} == {"WS-one", "WT-one"}
    assert "x" * 100 not in repr(state)

    folds = []
    real_fold = author_history._fold
    author_history._fold = lambda *a, **k: (folds.append(1), real_fold(*a, **k))[1]
    try:
        prior_offset = state["offset"]
        with talk.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"record": "writing-reply", "id": "other-later",
                                     "project": "unrelated", "text": "y" * 1024,
                                     "ts": "2026-09-30T10:04:00Z"}) + "\n")
        assert author_history.history("book", {}, repo_root=tmp_path) == first
        assert folds == [], "unrelated append advances the cursor without a project refold"
        assert state["offset"] > prior_offset and len(state["rows"]) == 2
    finally:
        author_history._fold = real_fold


def test_late_session_and_turn_links_recover_prior_unscoped_rows(tmp_path: Path) -> None:
    _fixture(tmp_path)
    talk = tmp_path / "contract" / "talk.jsonl"
    talk.write_text(json.dumps({"record": "writing-reply", "id": "WR-late",
                                "turn_id": "WT-late", "text": "Late linked reply.",
                                "ts": "2026-09-30T10:03:00Z"}) + "\n", encoding="utf-8")
    _clear()
    before = author_history.history("book", {}, repo_root=tmp_path)
    assert all(row["id"] != "activity:journal:WR-late" for row in before["items"])
    with talk.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"record": "writing-turn", "id": "WT-late",
                                 "session_id": "WS-late", "provider_settings": {
                                     "provider": "codex", "model": "recorded-model"},
                                 "text": "Late request.", "ts": "2026-09-30T10:02:00Z"}) + "\n")
        stream.write(json.dumps({"record": "writing-session", "id": "WS-late",
                                 "project": "book", "role": "author",
                                 "ts": "2026-09-30T10:01:00Z"}) + "\n")
    after = author_history.history("book", {}, repo_root=tmp_path)
    reply = next(row for row in after["items"] if row["id"] == "activity:journal:WR-late")
    assert reply["summary"] == "Late linked reply."
    assert reply["actor"] == {"label": None, "kind": "agent", "provider": "codex",
                               "model": "recorded-model", "role": "author"}
    assert reply["conversation"] == {"session_id": "WS-late", "turn_id": "WT-late"}


def test_direct_project_row_recovers_earlier_turn_context(tmp_path: Path) -> None:
    _fixture(tmp_path)
    talk = tmp_path / "contract" / "talk.jsonl"
    talk.write_text(json.dumps({"record": "writing-turn", "id": "WT-context",
                                "provider_settings": {"provider": "codex", "model": "context-model"},
                                "text": "Context request.", "ts": "2026-09-30T10:02:00Z"}) + "\n",
                    encoding="utf-8")
    _clear()
    author_history.history("book", {}, repo_root=tmp_path)
    with talk.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"record": "writing-reply", "id": "WR-direct",
                                 "turn_id": "WT-context", "project": "book",
                                 "text": "Direct project reply.",
                                 "ts": "2026-09-30T10:03:00Z"}) + "\n")
    reply = next(row for row in author_history.history("book", {}, repo_root=tmp_path)["items"]
                 if row["id"] == "activity:journal:WR-direct")
    assert reply["actor"] == {"label": None, "kind": "agent", "provider": "codex",
                               "model": "context-model"}


def test_partial_tail_and_same_size_replacement_preserve_freshness(tmp_path: Path) -> None:
    _fixture(tmp_path)
    talk = tmp_path / "contract" / "talk.jsonl"
    _clear()
    author_history.history("book", {}, repo_root=tmp_path)
    partial = json.dumps({"record": "writing-reply", "id": "WR-partial", "turn_id": "WT-one",
                          "project": "book", "text": "First body.",
                          "ts": "2026-09-30T10:03:00Z"})
    with talk.open("a", encoding="utf-8") as stream:
        stream.write(partial)
    assert all(row["id"] != "activity:journal:WR-partial"
               for row in author_history.history("book", {}, repo_root=tmp_path)["items"])
    with talk.open("a", encoding="utf-8") as stream:
        stream.write("\n")
    assert author_history.record("book", "WR-partial", repo_root=tmp_path)["text"] == "First body."

    raw = talk.read_text(encoding="utf-8")
    changed = raw.replace("First body.", "Other body.")
    assert len(changed) == len(raw)
    talk.write_text(changed, encoding="utf-8")
    assert author_history.record("book", "WR-partial", repo_root=tmp_path)["text"] == "Other body."

    replacement = talk.with_suffix(".replacement")
    replacement.write_text(json.dumps({"record": "writing-reply", "id": "WR-replaced",
                                       "project": "book", "text": "Replacement body.",
                                       "ts": "2026-09-30T10:04:00Z"}) + "\n", encoding="utf-8")
    os.replace(replacement, talk)
    replaced = author_history.history("book", {}, repo_root=tmp_path)
    assert [row["id"] for row in replaced["items"] if row["owner"] == "journal"] == [
        "activity:journal:WR-replaced"]


def test_cold_scan_does_not_adopt_a_post_scan_append_identity(tmp_path: Path,
                                                              monkeypatch) -> None:
    _fixture(tmp_path)
    talk = tmp_path / "contract" / "talk.jsonl"
    _clear()
    real_identity = record_owner._project._talk_file_identity
    calls = 0

    def racing_identity(path):
        nonlocal calls
        calls += 1
        if calls == 3:
            with talk.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"record": "writing-reply", "id": "WR-cold-race",
                                         "turn_id": "WT-one", "project": "book",
                                         "text": "Arrived after the cold scan.",
                                         "ts": "2026-09-30T10:03:00Z"}) + "\n")
        return real_identity(path)

    monkeypatch.setattr(record_owner._project, "_talk_file_identity", racing_identity)
    first = author_history.history("book", {}, repo_root=tmp_path)
    assert all(row["id"] != "activity:journal:WR-cold-race" for row in first["items"])
    state = author_history._TALK_CACHE[(str(tmp_path.resolve()), "book")]
    assert state["settled"] is False and state["offset"] < talk.stat().st_size
    second = author_history.history("book", {}, repo_root=tmp_path)
    assert any(row["id"] == "activity:journal:WR-cold-race" for row in second["items"])


def test_suffix_scan_does_not_adopt_a_post_scan_append_identity(tmp_path: Path,
                                                                monkeypatch) -> None:
    _fixture(tmp_path)
    talk = tmp_path / "contract" / "talk.jsonl"
    _clear()
    author_history.history("book", {}, repo_root=tmp_path)
    with talk.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"record": "writing-reply", "id": "other-trigger",
                                 "project": "unrelated", "text": "trigger"}) + "\n")
    real_identity = record_owner._project._talk_file_identity
    calls = 0

    def racing_identity(path):
        nonlocal calls
        calls += 1
        if calls == 2:
            with talk.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"record": "writing-reply", "id": "WR-suffix-race",
                                         "turn_id": "WT-one", "project": "book",
                                         "text": "Arrived after the suffix scan.",
                                         "ts": "2026-09-30T10:03:00Z"}) + "\n")
        return real_identity(path)

    monkeypatch.setattr(record_owner._project, "_talk_file_identity", racing_identity)
    first = author_history.history("book", {}, repo_root=tmp_path)
    assert all(row["id"] != "activity:journal:WR-suffix-race" for row in first["items"])
    state = author_history._TALK_CACHE[(str(tmp_path.resolve()), "book")]
    assert state["settled"] is False and state["offset"] < talk.stat().st_size
    second = author_history.history("book", {}, repo_root=tmp_path)
    assert any(row["id"] == "activity:journal:WR-suffix-race" for row in second["items"])


def test_a_page_a_caller_edits_cannot_change_the_next_page(tmp_path: Path) -> None:
    """EVERY value the doors hand out, not only ``items``.

    The first version of this test touched ``items`` alone, and the judge's probe
    (``wave1/storage-latency-judge1/probes/alias_probe.py``) found that ``coverage`` was
    handed out as the live object inside the cached fold and ``record()`` returned the
    cached item itself: a caller that edited either changed every later page for the life
    of the process.  Before the index these were rebuilt per call, so the aliasing is the
    index's own hazard and belongs in the index's own test.
    """
    _fixture(tmp_path)
    _clear()
    page = author_history.history("book", {}, repo_root=tmp_path)
    assert page["items"], "the fixture produced no activity"
    assert page["coverage"], "the fixture produced no coverage"
    page["items"][0]["summary"] = "MUTATED BY A CALLER"
    page["items"][0]["targets"] = []
    page["coverage"][0]["label"] = "COVERAGE MUTATED BY A CALLER"
    page["coverage"][0]["poisoned"] = True
    again = author_history.history("book", {}, repo_root=tmp_path)
    assert again["items"][0]["summary"] != "MUTATED BY A CALLER"
    assert "MUTATED BY A CALLER" not in json.dumps(again["coverage"])
    assert "poisoned" not in json.dumps(again["coverage"])

    # The record view: the item it returns is a copy, and so is the stored row beside it.
    ident = again["items"][0]["id"]
    view = author_history.record("book", ident, repo_root=tmp_path)
    view["item"]["summary"] = "RECORD VIEW MUTATED BY A CALLER"
    view["record"]["project"] = "RECORD ROW MUTATED BY A CALLER"
    third = author_history.history("book", {}, repo_root=tmp_path)
    assert third["items"][0]["summary"] != "RECORD VIEW MUTATED BY A CALLER"
    assert "MUTATED BY A CALLER" not in json.dumps(
        author_history.record("book", ident, repo_root=tmp_path))

    # The detail view, including the nested lists inside its item.
    detail = author_history.detail("book", ident, repo_root=tmp_path)
    targets = detail.get("item", {}).get("targets")
    if isinstance(targets, list) and targets:
        targets[0]["poisoned"] = True
    fourth = author_history.history("book", {}, repo_root=tmp_path)
    assert "poisoned" not in json.dumps(fourth["items"])


def _save(manuscript: Path, name: str, body: str) -> Path:
    """One banked editor save, as projection_viewer writes it: a directory, then a file
    inside it (``projection_viewer.py:740-750``)."""
    directory = manuscript / "editor_saves" / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "VERSION.json"
    path.write_text(json.dumps({
        "version_id": name, "file": "main.tex", "author": "author",
        "saved": "2026-09-30T10:30:00Z", "note": body}), encoding="utf-8")
    return path


def test_the_stamp_moves_when_a_file_the_fold_opens_is_rewritten_in_place(
        tmp_path: Path) -> None:
    """The property the index needs, stated as the property and not as ancestry.

    The earlier test accepted any path with a declared directory somewhere in its
    ``parents``, which is weaker: ``editor_saves/<save>/VERSION.json`` passed it while a
    stamp that listed only the directory and its immediate children would not have moved
    when that file was rewritten in place -- same parent mtime, same parent size -- and
    the index would have served a stale page in silence.  So the assertion is now the one
    that matters: rewrite each file the fold opens, same byte length, and the stamp moves.
    """
    _fixture(tmp_path)
    manuscript = tmp_path / "sources" / "book"
    _save(manuscript, "save-2026-09-30_103000-1", "aaaa")
    _clear()

    seen: list[Path] = []
    real_open, real_text, real_bytes = builtins.open, Path.read_text, Path.read_bytes

    def note(value) -> None:
        try:
            seen.append(Path(value).resolve())
        except (TypeError, ValueError, OSError):
            pass

    builtins.open = lambda file, *a, **k: (note(file), real_open(file, *a, **k))[1]
    Path.read_text = lambda self, *a, **k: (note(self), real_text(self, *a, **k))[1]
    Path.read_bytes = lambda self, *a, **k: (note(self), real_bytes(self, *a, **k))[1]
    try:
        author_history._fold("book", tmp_path)
    finally:
        builtins.open, Path.read_text, Path.read_bytes = real_open, real_text, real_bytes

    inside = sorted({path for path in seen
                     if str(path).startswith(str(tmp_path.resolve()))
                     and path.is_file()})
    assert inside, "the fold read nothing inside the fixture"
    assert any(path.name == "VERSION.json" for path in inside), (
        "the fixture must exercise a grandchild of a declared directory")

    for path in inside:
        before = author_history._source_stamp("book", tmp_path)
        raw = path.read_bytes()
        # Rewritten IN PLACE, same length: nothing about any parent directory moves.
        stat = path.stat()
        try:
            if raw:
                path.write_bytes(raw[:-1] + (b"b" if raw[-1:] != b"b" else b"c"))
                assert len(path.read_bytes()) == len(raw), "same length, in place"
            else:
                # An empty file cannot be rewritten to a different byte, so the change is
                # its mtime alone -- still the file, still nothing about any parent.
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
            after = author_history._source_stamp("book", tmp_path)
        finally:
            path.write_bytes(raw)          # the next path's stamp needs a live fixture
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        assert after != before, (
            f"{path.relative_to(tmp_path)} is read by the fold and rewriting it does not "
            f"move the stamp, so the index would serve a stale page; extend "
            f"author_history._source_stamp to reach it")


def test_the_index_is_bounded_in_entries(tmp_path: Path) -> None:
    """``views`` is capped at ``_VIEW_LIMIT``; the index itself has to be capped too.

    One entry retains the whole fold -- 20.1 MiB measured for the author's own project
    (``wave1/storage-latency/probes/fold_retention.py``) -- and the app is long-running,
    so an index that never evicted would retain the fold of every project whose history
    was ever read: 21 registered projects, roughly 0.41 GiB the base tree retained none
    of.  The bound is the most recent ``_INDEX_LIMIT`` (root, project) pairs.
    """
    projects = []
    for index in range(author_history._INDEX_LIMIT + 2):
        root = tmp_path / f"root{index}"
        root.mkdir()
        _fixture(root)
        projects.append(root)
    _clear()
    for root in projects:
        author_history.history("book", {}, repo_root=root)
        assert len(author_history._ALL_CACHE) <= author_history._INDEX_LIMIT

    kept = [key for key, _ in author_history._ALL_CACHE.items()]
    assert len(kept) == author_history._INDEX_LIMIT
    assert set(author_history._TALK_CACHE) == set(author_history._ALL_CACHE), (
        "project talk rows share the existing index's eviction ownership")
    assert [str(root) for root in projects[-author_history._INDEX_LIMIT:]] == [
        key[0] for key in kept], "the oldest entry is the one evicted"

    # An evicted entry is a refold, not a wrong answer.
    folds = []
    real_fold = author_history._fold
    author_history._fold = lambda *a, **k: (folds.append(1), real_fold(*a, **k))[1]
    try:
        again = author_history.history("book", {}, repo_root=projects[0])
        assert len(folds) == 1, "the evicted entry must be refolded, not served stale"
        assert again["items"], "the refold answers the same page"
    finally:
        author_history._fold = real_fold


def test_artifact_activity_reuses_guarded_source_basis_and_never_loads_global_rich_records(tmp_path, monkeypatch):
    from laplace.native import tools as writing_tools
    from laplace.writing import session_reads
    _fixture(tmp_path);_clear()
    created=[]
    for number in range(4):
        created.append(writing_tools.execute(tmp_path,'book','work','store_artifact',
            {'path':f'result{number}.txt','before':None,'content':'Exact result','reason':'Fixture'}))
    from laplace.projects import artifacts
    original=artifacts.context;seen=[]
    monkeypatch.setattr(artifacts,'context',lambda *a,**k:(seen.append(1),original(*a,**k))[1])
    monkeypatch.setattr(session_reads,'_records',lambda *a,**k:(_ for _ in ()).throw(AssertionError('rich hydration')))
    result=author_history.history('book',{'limit':20},tmp_path)
    targets=[target for row in result['items'] for target in row.get('targets',[]) if target['kind']=='artifact']
    assert len(seen)==1 and len(targets)==4
    assert {target['recorded_revision'] for target in targets}=={row['revision'] for row in created}


def test_legacy_telemetry_reuses_derived_facets_but_observes_run_owner_and_refreshes_on_append(tmp_path,monkeypatch):
    _fixture(tmp_path);_clear();counts=[];real=author_history._telemetry_tool_calls
    monkeypatch.setattr(author_history,'_telemetry_tool_calls',lambda *a,**k:(counts.append(1),real(*a,**k))[1])
    runs=[]
    monkeypatch.setattr(author_history,'_telemetry_runs',lambda *a,**k:[{'id':'run','observed':len(runs)}])
    first=author_history.telemetry('book',{},tmp_path);runs.append(1)
    second=author_history.telemetry('book',{},tmp_path)
    assert len(counts)==1 and second['runs'][0]['observed']==1
    second['totals']['activity']=999
    assert author_history.telemetry('book',{},tmp_path)['totals']==first['totals']
    path=tmp_path/'contract/talk.jsonl'
    with path.open('a') as stream:stream.write(json.dumps({'record':'writing-tool-read','id':'READ-new','project':'book','turn_id':'WT-one','operation':'source','ts':'2026-10-01T00:00:00Z'})+'\n')
    latest=author_history.telemetry('book',{},tmp_path)
    assert len(counts)==2 and latest['tool_calls']['total']==1
