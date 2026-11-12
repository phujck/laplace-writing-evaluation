"""test_segment.py - the three laws, per segmenter, on synthetic fixtures.

Coverage is exact (leaf spans tile the node's bytes with no gap and no overlap), the cap is
enforced with every over-cap leaf naming why it could not be split, structured sources never
reach the raw fallback, nesting is consistent, and the same bytes cut twice produce identical
span ids.
"""

from __future__ import annotations

import pytest

from atlas.errors import CapViolation, CoverageViolation, StructureViolation
from atlas.schema import Span
from atlas.segment import (
    check_cap,
    check_coverage,
    check_nesting,
    check_structure,
    segment_bytes,
    segmenter_for,
)

HASH = "sha256:" + "0" * 64
TARGET = 64          # 256 bytes
CAP = 128            # 512 bytes


def run(path: str, data: bytes, target: int = TARGET, cap: int = CAP):
    return segment_bytes(path, path, HASH, data, target, cap)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

MARKDOWN = (
    "Preamble line before any heading.\n\n"
    + "# Top\n\nIntro body under Top.\n\n"
    + "## Alpha\n\n" + ("alpha body paragraph. " * 40) + "\n\n"
    + "## Beta\n\n" + ("beta body paragraph. " * 40) + "\n\n"
    + "### Beta child\n\n" + ("nested body. " * 40) + "\n"
).encode("utf-8")

PYTHON = (
    '"""Module docstring."""\n\nimport os\n\n\n'
    + 'def first():\n    """First docstring."""\n' + "    x = 1\n" * 40 + "    return x\n\n\n"
    + "@decorator\ndef second():\n" + "    y = 2\n" * 40 + "    return y\n\n\n"
    + "class Third:\n    \"\"\"Third docstring.\"\"\"\n" + "    z = 3\n" * 40
).encode("utf-8")

JSON_DOC = (
    '{\n  "alpha": "' + "a" * 400 + '",\n'
    '  "beta": {"inner_one": "' + "b" * 400 + '", "inner_two": "' + "c" * 400 + '"},\n'
    '  "gamma": [' + ", ".join(f'"{i}"' for i in range(200)) + ']\n}\n'
).encode("utf-8")

JSONL = ("\n".join('{"row": %d, "payload": "%s"}' % (i, "p" * 100) for i in range(30))
         + "\n").encode("utf-8")

YAML = (
    "top_one: value\n"
    "top_two:\n" + "  nested_key: nested value\n" * 40
    + "top_three: " + "z" * 400 + "\n"
    + "---\n"
    + "second_doc: yes\n"
).encode("utf-8")

TEX = (
    "\\documentclass{article}\n\\begin{document}\n"
    + "\\section{One}\n" + ("section one prose. " * 40) + "\n\n"
    + "\\subsection{One A}\n" + ("subsection prose. " * 40) + "\n\n"
    + "\\section{Two}\n" + ("section two prose. " * 40) + "\n"
    + "\\end{document}\n"
).encode("utf-8")

PLAIN = ("plain text with line breaks. " * 200).encode("utf-8")

UNBROKEN = b"x" * 4000            # no newline anywhere: unsplittable by any prose boundary

CASES = {
    "doc.md": MARKDOWN,
    "mod.py": PYTHON,
    "data.json": JSON_DOC,
    "rows.jsonl": JSONL,
    "conf.yaml": YAML,
    "paper.tex": TEX,
    "notes.txt": PLAIN,
}


# ---------------------------------------------------------------------------
# routing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ("a/doc.md", "markdown/1"), ("a/mod.py", "code/1"), ("a/x.mjs", "code/1"),
    ("a/data.json", "structured-json/1"), ("a/rows.jsonl", "structured-jsonl/1"),
    ("a/conf.yaml", "structured-yaml/1"), ("a/conf.yml", "structured-yaml/1"),
    ("a/paper.tex", "tex/1"), ("a/notes.txt", "fallback/1"), ("a/thing.css", "fallback/1"),
])
def test_routing(path, expected):
    assert segmenter_for(path).segmenter_id == expected


# ---------------------------------------------------------------------------
# the laws
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", sorted(CASES))
def test_coverage_is_an_exact_partition(path):
    data = CASES[path]
    result = run(path, data)
    leaves = sorted((s for s in result.spans if s.is_leaf), key=lambda s: s.start)
    assert leaves, path
    assert leaves[0].start == 0
    assert leaves[-1].end == len(data)
    for prev, nxt in zip(leaves, leaves[1:], strict=False):
        assert prev.end == nxt.start, f"{path}: gap or overlap at {prev.end}"
    assert check_coverage(path, len(data), result.spans) == len(data)


@pytest.mark.parametrize("path", sorted(CASES))
def test_cap_holds_or_is_named(path):
    result = run(path, CASES[path])
    over = check_cap(path, result.spans, CAP)
    for span in result.spans:
        if span.is_leaf and span.est_tokens > CAP:
            assert span.meta.get("oversize_reason"), path
    assert len(over) == len(result.oversize)


@pytest.mark.parametrize("path", sorted(CASES))
def test_nesting_is_consistent(path):
    result = run(path, CASES[path])
    check_nesting(path, result.spans)
    by_id = {s.span_id: s for s in result.spans}
    for span in result.spans:
        if span.parent_span:
            parent = by_id[span.parent_span]
            assert parent.start <= span.start and span.end <= parent.end
            assert not parent.is_leaf


@pytest.mark.parametrize("path", sorted(CASES))
def test_determinism(path):
    data = CASES[path]
    first = run(path, data)
    second = run(path, data)
    assert [s.span_id for s in first.spans] == [s.span_id for s in second.spans]
    assert [s.to_dict() for s in first.spans] == [s.to_dict() for s in second.spans]


@pytest.mark.parametrize("path", sorted(CASES))
def test_span_ids_are_the_hash_of_their_fields(path):
    for span in run(path, CASES[path]).spans:
        assert span.span_id == Span.compute_id(HASH, span.start, span.end,
                                               span.segmenter_id, span.seg_version)


@pytest.mark.parametrize("path", ["data.json", "rows.jsonl", "conf.yaml"])
def test_structured_never_reaches_the_fallback(path):
    result = run(path, CASES[path])
    assert all(not s.segmenter_id.startswith("fallback") for s in result.spans)
    check_structure(path, result.spans)


def test_structure_law_fires_when_a_structured_source_falls_back():
    """The check itself has teeth: fallback spans presented as a .json source are refused."""
    fallback_spans = run("notes.txt", PLAIN).spans
    assert all(s.segmenter_id == "fallback/1" for s in fallback_spans)
    with pytest.raises(StructureViolation) as exc:
        check_structure("data.json", fallback_spans)
    assert exc.value.reason == "segmentation-structure-violation"


# ---------------------------------------------------------------------------
# per-segmenter behaviour
# ---------------------------------------------------------------------------

def test_markdown_carries_the_heading_trail_and_nests():
    result = run("doc.md", MARKDOWN)
    trails = [tuple(s.trail) for s in result.spans if s.is_leaf]
    assert ("Top", "Alpha") in trails
    assert ("Top", "Beta") in trails or ("Top", "Beta", "Beta child") in trails
    assert any(not s.is_leaf for s in result.spans), "a split section emits a parent span"


def test_markdown_heading_at_byte_zero_is_the_root_of_every_leaf_trail():
    data = (
        "# Root\n\nroot body\n\n"
        "## First\n\n" + ("first body. " * 30) + "\n\n"
        "## Second\n\n" + ("second body. " * 30) + "\n"
    ).encode("utf-8")
    result = run("root.md", data, target=24, cap=64)
    trails = [tuple(span.trail) for span in result.spans if span.is_leaf]
    assert trails
    assert all(trail and trail[0] == "Root" for trail in trails)
    assert any(trail == ("Root", "First") for trail in trails)
    assert any(trail == ("Root", "Second") for trail in trails)


def test_markdown_ignores_headings_inside_fences():
    data = ("# Real\n\ntext\n\n```\n# not a heading\n```\n\nmore text\n").encode("utf-8")
    result = run("doc.md", data, target=4, cap=8)
    for span in result.spans:
        assert "not a heading" not in " ".join(span.trail)


def test_code_attaches_the_docstring_to_its_symbol():
    result = run("mod.py", PYTHON)
    named = [s for s in result.spans if s.trail and s.trail[-1] == "first"]
    assert named
    span = named[0]
    assert b"First docstring." in PYTHON[span.start:span.end]


def test_code_binds_a_decorator_to_the_symbol_below_it():
    result = run("mod.py", PYTHON)
    starts = [s.start for s in result.spans if s.is_leaf]
    decorator_at = PYTHON.index(b"@decorator")
    def_at = PYTHON.index(b"def second")
    assert def_at not in starts, "the decorated def must not start its own span"
    assert any(s <= decorator_at for s in starts)


def test_json_emits_a_key_inventory_and_never_a_raw_head():
    result = run("data.json", JSON_DOC)
    inventories = [s for s in result.spans if s.kind in ("json_object", "json_array")]
    assert inventories, "an object split into members must emit a key-inventory span"
    root = inventories[0]
    assert root.is_leaf is False
    assert root.meta["container"] == "object"
    assert set(root.meta["keys"]) >= {"alpha", "beta", "gamma"}
    assert root.meta["member_count"] == 3


def test_json_leaves_carry_key_paths():
    result = run("data.json", JSON_DOC)
    trails = {tuple(s.trail) for s in result.spans if s.is_leaf}
    assert any(t and t[0] == "alpha" for t in trails)
    assert any(t and t[0] == "beta" for t in trails)


def test_jsonl_cuts_only_on_row_boundaries():
    result = run("rows.jsonl", JSONL)
    assert len(result.spans) == len(JSONL.splitlines())
    for row, span in enumerate(result.spans):
        if span.start:
            assert JSONL[span.start - 1:span.start] == b"\n"
        assert span.kind == "jsonl_row"
        assert span.meta == {"row_start": row, "row_end": row}
        assert JSONL[span.end - 1:span.end] == b"\n"


def test_jsonl_blank_and_invalid_rows_remain_exact_individual_spans():
    data = b'{"record":"x","id":"a"}\n\nnot-json\n'
    result = run("governance.jsonl", data)
    assert [(span.start, span.end) for span in result.spans] == [(0, 24), (24, 25), (25, 34)]
    assert b"".join(data[span.start:span.end] for span in result.spans) == data


def test_yaml_records_the_nested_structure_bound():
    result = run("conf.yaml", YAML)
    reasons = {m["reason"] for m in result.misses}
    assert "segmentation-miss/yaml-nested-structure" in reasons
    trails = {tuple(s.trail) for s in result.spans}
    assert any("top_two" in t for t in trails)


def test_tex_nests_subsections_under_sections():
    result = run("paper.tex", TEX)
    trails = [tuple(s.trail) for s in result.spans if s.is_leaf]
    assert any(t[:1] == ("One",) for t in trails)
    assert any("One A" in t for t in trails)


def test_fallback_records_a_miss_and_carries_overlap_context():
    result = run("notes.txt", PLAIN)
    assert {m["reason"] for m in result.misses} == {"segmentation-miss/no-structural-reader"}
    for span in result.spans:
        assert span.meta["context_start"] <= span.start


def test_fallback_never_emits_an_oversize_span():
    result = run("blob.bin", UNBROKEN)
    assert result.oversize == []
    assert all(s.est_tokens <= CAP for s in result.spans if s.is_leaf)


def test_unsplittable_markdown_is_named_oversize_not_sliced():
    result = run("doc.md", UNBROKEN)
    assert len(result.oversize) == 1
    assert result.oversize[0]["reason"] == "markdown-block-has-no-paragraph-or-line-break"
    assert len([s for s in result.spans if s.is_leaf]) == 1


def test_empty_node_produces_no_spans():
    assert run("doc.md", b"").spans == []


def test_whole_small_file_is_one_leaf():
    data = b"# Tiny\n\nshort.\n"
    result = run("doc.md", data)
    assert len(result.spans) == 1
    assert result.spans[0].is_leaf
    assert (result.spans[0].start, result.spans[0].end) == (0, len(data))


# ---------------------------------------------------------------------------
# the law checkers themselves
# ---------------------------------------------------------------------------

def test_check_coverage_catches_a_hole():
    node = "a.md"
    spans = [Span(span_id=Span.compute_id(HASH, 0, 4, "markdown/1", "seg/1"), node_id=node,
                  source_content_hash=HASH, segmenter_id="markdown/1", seg_version="seg/1",
                  start=0, end=4, est_tokens=1, is_leaf=True, parent_span=None,
                  kind="md_block")]
    with pytest.raises(CoverageViolation):
        check_coverage(node, 10, spans)


def test_check_cap_catches_an_unnamed_oversize():
    span = Span(span_id=Span.compute_id(HASH, 0, 4000, "markdown/1", "seg/1"), node_id="a.md",
                source_content_hash=HASH, segmenter_id="markdown/1", seg_version="seg/1",
                start=0, end=4000, est_tokens=1000, is_leaf=True, parent_span=None,
                kind="md_block")
    with pytest.raises(CapViolation):
        check_cap("a.md", [span], CAP)
