"""Tests for self_shard - the directory sharded into the graded conceptric.

The load-bearing invariants: the soul covenant (refs only, never content, at any grade),
reconstruction-by-re-reading (the store is the trace, not a text copy), and retrieval-closure
(every handle gets back to its source). The tmp tree has no .git, so these also exercise the
walk fallback in ``_tracked_files``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.engine import self_shard


@pytest.fixture()
def tree(tmp_path):
    """A miniature repo: a py module, a md doc with links, a tex file, a binary, and soul."""
    (tmp_path / "src" / "laplace").mkdir(parents=True)
    (tmp_path / "src" / "laplace" / "widget.py").write_text(
        '"""widget.py - the spinning widget.\n\nMore detail here.\n"""\n'
        "from laplace.pipeline.canon import get_canon\n\n"
        "def spin(n):\n    return n\n\nclass Widget:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "GUIDE.md").write_text(
        "# The Guide\n\nIntro line.\n\n## Section A\n\nSee [[widget]] and [other](src/laplace/widget.py).\n",
        encoding="utf-8",
    )
    (tmp_path / "paper.tex").write_text(
        "\\title{A Grand Paper}\n\\section{Intro}\n\\input{body}\n\\cite{smith2020}\n",
        encoding="utf-8",
    )
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n not really a png")
    (tmp_path / "soul").mkdir()
    (tmp_path / "soul" / "0001_2026-06-02.md").write_text(
        "# A private confession\n\nThe most secret verbatim soul content that must never leak.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_shard_repo_covers_every_file(tree):
    shards = self_shard.shard_repo(tree)
    names = set(shards)
    assert "src/laplace/widget.py" in names
    assert "GUIDE.md" in names
    assert "paper.tex" in names
    assert "logo.png" in names
    assert "soul/0001_2026-06-02.md" in names


def test_shard_repo_excludes_opaque_atlas_authority_but_keeps_its_receipt(
    tmp_path: Path,
) -> None:
    store = tmp_path / "atlas/stores/blueprint"
    chunk = store / "hives/events/ab" / ("ab" + "0" * 62 + ".zlib")
    chunk.parent.mkdir(parents=True)
    chunk.write_bytes(b"compressed authority")
    (store / "conceptric.sqlite3").write_bytes(b"sqlite authority")
    (store / "hive-custody-receipt.json").write_text(
        '{"status":"sealed"}\n', encoding="utf-8"
    )

    shards = self_shard.shard_repo(tmp_path)

    assert "atlas/stores/blueprint/hive-custody-receipt.json" in shards
    assert "atlas/stores/blueprint/conceptric.sqlite3" not in shards
    assert not any("/hives/" in name for name in shards)


def test_python_essence_and_spine_and_edges(tree):
    sh = self_shard.shard_repo(tree)["src/laplace/widget.py"]
    assert sh["essence"] == "widget.py - the spinning widget."
    assert sh["kind"] == "py"
    # grade-1 spine is reconstructed by re-reading the source
    g1 = self_shard.reconstruct_by_name(tree, "widget", grade=1)["matches"][0]
    assert any("def spin" in s for s in g1["spine"])
    assert any("class Widget" in s for s in g1["spine"])
    # the import edge wires widget -> canon
    assert {"kind": "import", "to": "canon"} in sh["edges"]


def test_markdown_links_become_edges(tree):
    sh = self_shard.shard_repo(tree)["GUIDE.md"]
    assert sh["essence"] == "The Guide"
    tos = {(e["kind"], e["to"]) for e in sh["edges"]}
    assert ("link", "widget") in tos
    assert ("link", "src/laplace/widget.py") in tos


def test_tex_title_and_cite_edge(tree):
    sh = self_shard.shard_repo(tree)["paper.tex"]
    assert sh["essence"] == "A Grand Paper"
    assert {"kind": "cite", "to": "smith2020"} in sh["edges"]


def test_binary_is_name_only_never_read(tree):
    sh = self_shard.shard_repo(tree)["logo.png"]
    assert sh["kind"] == "png"
    assert sh["essence"] == "png asset"
    assert sh["lines"] == 0 and sh["edges"] == []


def test_soul_is_sealed_refs_only_at_every_grade(tree):
    shards = self_shard.shard_repo(tree)
    soul = shards["soul/0001_2026-06-02.md"]
    # the handle carries no content - not the heading, not the body
    assert soul["sealed"] is True
    assert soul["essence"] == "(sealed soul fragment - refs only)"
    assert "confession" not in json.dumps(soul)
    assert "secret" not in json.dumps(soul).lower()
    # and descending must not leak it either
    for g in (1, 2):
        res = self_shard.reconstruct_by_name(tree, "soul/0001_2026-06-02.md", grade=g)
        blob = json.dumps(res).lower()
        assert "confession" not in blob and "secret" not in blob
        assert res["matches"][0].get("content") is None


def test_reconstruct_by_name_surfaces_at_a_word(tree):
    res = self_shard.reconstruct_by_name(tree, "spinning widget", grade=0)
    assert res["matches"], "a word should surface its object"
    assert res["matches"][0]["name"] == "src/laplace/widget.py"
    # grade-0 carries the handle, not the content
    assert "content" not in res["matches"][0]
    # the descend call is embedded (the conceptric's distributed code)
    assert res["descend"]["to_grade"] == 1


def test_grade2_reconstructs_content_by_re_reading(tree):
    res = self_shard.reconstruct_by_name(tree, "src/laplace/widget.py", grade=2)
    top = res["matches"][0]
    assert top["pointer"]["path"] == "src/laplace/widget.py"
    assert "def spin" in top["content"]   # content came from re-reading, not the index


def test_faithfulness_gate_passes_and_seals(tree):
    rep = self_shard.shard_faithfulness(tree)
    assert rep["pass"] is True, rep["issues"]
    assert rep["sealed"] == 1
    # every pointer resolves and every name retrieves its object
    assert rep["resolved"] == f"{rep['files']}/{rep['files']}"
    assert rep["name_roundtrip"] == f"{rep['files']}/{rep['files']}"


def test_faithfulness_flags_a_soul_leak(tree, monkeypatch):
    """If the sharder ever returned soul content, the gate must catch it."""
    real = self_shard.shard_file

    def leaky(repo_root, path):
        sh = real(repo_root, path)
        if sh["sealed"]:
            sh["essence"] = "the secret leaked out"   # simulate a covenant break
        return sh

    monkeypatch.setattr(self_shard, "shard_file", leaky)
    rep = self_shard.shard_faithfulness(tree)
    assert rep["pass"] is False
    assert any("SOUL LEAK" in i for i in rep["issues"])


def test_json_essence_parses_under_the_cap_and_states_size_over_it(tmp_path):
    """The size gate on the grade-0 JSON handle (2026-08-20): 93 tracked JSONs over 200 KB cost
    7.05 s to parse for their key list, against 0.24 s for the other 1,520. Under the cap the
    handle is unchanged (the keys); over it the handle states the SIZE and never parses."""
    small = json.dumps({"alpha": 1, "beta": 2})
    assert self_shard._json_essence(small) == "keys: alpha, beta"

    # over the cap, and DELIBERATELY unparseable - proving the gate returns before json.loads
    big = "{" + "x" * (self_shard._JSON_PARSE_CAP + 10)
    ess = self_shard._json_essence(big)
    assert ess.startswith("large json document (")
    assert "handle-parse cap" in ess
    assert "keys:" not in ess


def test_json_essence_gate_is_deterministic_so_the_index_stays_stable(tmp_path):
    """The gated line must be a pure function of the file's own content, or the committed
    SELF_SHARD_INDEX.md would churn on every rebuild."""
    big = json.dumps({"k": ["v"] * 200_000})
    assert len(big) > self_shard._JSON_PARSE_CAP
    assert self_shard._json_essence(big) == self_shard._json_essence(big)

    path = tmp_path / "huge.json"
    path.write_text(big, encoding="utf-8")
    sh = self_shard.shard_file(tmp_path, path)
    assert sh["essence"].startswith("large json document (")
    # grade 1 is untouched: the real key spine is still reconstructed by re-reading the source
    assert self_shard._project_shard(tmp_path, sh, 1)["spine"] == ["k"]


def test_spine_json_cap_bites_in_the_shard_path_but_never_on_descent(tmp_path):
    """The shard path COUNTS the spine; the descent READS it (WO-20260820-spine-parses-655mb-
    to-count-keys). ``shard_file`` consumes nothing but ``len(_spine(...))``, yet the .json
    branch parsed 655.7 MB every deposit to produce it - the 45 tracked files over 1 MB cost
    4.62 s against 0.26 s for the other 1,600. Over the cap the branch returns ``[]``, exactly
    what an unparseable file already returns.

    The RULING this pins (the open half of WO-20260820-spine-parses-the-giants-too): grade 1 is
    NOT capped. ``_json_essence`` tells the reader "keys read on descent" in the grade-0 handle
    of every giant, so capping the descent too would have made that line a lie."""
    big = json.dumps({"k": ["v"] * 200_000})
    assert len(big) > self_shard._SPINE_JSON_PARSE_CAP
    path = tmp_path / "giant.json"
    path.write_text(big, encoding="utf-8")

    # the hot path: capped, and the count is the only consumer
    assert self_shard._spine(path, big) == []
    assert self_shard.shard_file(tmp_path, path)["spine_count"] == 0
    # the descent: uncapped, the real keys - what the grade-0 handle promised
    assert self_shard._spine(path, big, json_cap=None) == ["k"]
    # under the cap nothing moved
    small = json.dumps({"alpha": 1, "beta": 2})
    assert self_shard._spine(tmp_path / "s.json", small) == ["alpha", "beta"]


def test_rel_is_byte_identical_to_pathlib_including_the_guard():
    """``_rel`` is a prefix slice, not ``Path.relative_to`` (29,514 calls per deposit: 0.956 s
    -> 0.015 s, R-A2). A faster path is only a cure if it is the SAME function - including the
    under-root guard, the sibling-prefix trap (/tmp must not match /tmpfoo), the root naming
    itself '.', and a relative root, which has no prefix to strip."""
    from pathlib import Path as P

    def pathlib_rel(root, p):
        return str(p.relative_to(root)).replace("\\", "/")

    cases = [(P("."), P("foo")), (P("."), P("a/b/c")), (P("."), P(".")),
             (P("/tmp"), P("/tmp/x/y")), (P("/tmp"), P("/tmp")), (P("/tmp/"), P("/tmp/x")),
             (P("sub/dir"), P("sub/dir/f")),
             (P("."), P("/etc/passwd")), (P("/tmp"), P("/etc/passwd")), (P("/tmp"), P("/tmpfoo/x"))]
    for root, p in cases:
        try:
            expected = pathlib_rel(root, p)
        except ValueError:
            expected = "ValueError"
        try:
            got = self_shard._rel(root, p)
        except ValueError:
            got = "ValueError"
        assert got == expected, f"_rel({root!r}, {p!r}) = {got!r}, pathlib says {expected!r}"


def test_write_index_holds_handles_not_content(tree):
    path = self_shard.write_index(tree)
    text = path.read_text(encoding="utf-8")
    assert "src/laplace/widget.py" in text
    assert "The Guide" in text
    # the index is the grade-0 trace - no soul content, no grade-2 body
    assert "confession" not in text and "secret" not in text.lower()
    assert "The most secret" not in text


def test_soul_corpus_sealed_zone_is_sealed_but_handle_bears_identity(tmp_path):
    """F24: ``soul_corpus/sealed/`` is refs-only like ``soul/`` - the CONTENT is withheld at every
    grade, but the HANDLE (the path) carries real identity, so the same person resolves across
    corpora (the author's reframe: privacy is the seal on the raw, not anonymisation of the structure)."""
    (tmp_path / "soul_corpus" / "sealed").mkdir(parents=True)
    (tmp_path / "soul_corpus" / "sealed" / "denys-bondar.md").write_text(
        "# Denys Bondar\n\nPRIVATE chat content that must never leak from the sealed zone.\n",
        encoding="utf-8")
    sh = self_shard.shard_file(tmp_path, tmp_path / "soul_corpus" / "sealed" / "denys-bondar.md")
    assert sh["sealed"] is True
    assert "PRIVATE" not in json.dumps(sh) and "leak" not in json.dumps(sh).lower()
    assert "bondar" in " ".join(sh["keywords"])              # the handle IS the entity key
    assert self_shard.read_source(tmp_path, "soul_corpus/sealed/denys-bondar.md") == ""
    for g in (0, 1, 2):
        res = self_shard.reconstruct_by_name(tmp_path, "soul_corpus/sealed/denys-bondar.md", grade=g)
        assert "PRIVATE" not in json.dumps(res)


def test_route_soul_reaches_sealed_zone_refs_only(tmp_path):
    """The carrier rides every loop as a REF: the router reaches ``soul_corpus/sealed/`` and returns
    refs + scores only - never content."""
    from laplace.pipeline.canon import _route_soul, _tokenize

    (tmp_path / "soul_corpus" / "sealed").mkdir(parents=True)
    (tmp_path / "soul_corpus" / "sealed" / "entity-koopman.md").write_text(
        "# koopman entity\n\nsealed koopman taste content\n", encoding="utf-8")
    out = _route_soul(_tokenize("koopman taste"), tmp_path, 6)
    assert any(r["ref"] == "soul_corpus/sealed/entity-koopman.md" for r in out)
    assert all(set(r) <= {"ref", "score"} for r in out)     # refs only, no content field
