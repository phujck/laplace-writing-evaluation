"""D2 HELP COST (2026-10-15): the served default help keeps what a caller needs to act and names every moved value;
`help {operation, section}` returns that value exactly, through the same owner, natively and over HTTP. The held
cap (220,767 characters for the deployed operations' envelopes, tests/test_generated_contract.py) is met without
truncating anything: default + its sections reconstructs the complete rendering for every operation."""
import json
from urllib.parse import parse_qs, urlencode

import pytest

from laplace.web import authoring as a
from laplace.native import declarations as d, tools
from laplace.writing import operating as writing_operating
from laplace.writing import reads

OPERATIONS = sorted(reads.READS | reads.WRITES)


def _reconstruct(operation, default):
    """The full rendering from the default and its section reads only."""
    value = {key: item for key, item in default.items() if key not in {"sections", "input_summary", "acts_total", "outputs_total"}}
    for name in (default.get("sections") or {}).get("chars", {}):
        value[name] = d.help_payload(operation, permitted=default["permitted"], section=name)["value"]
    return value


@pytest.mark.parametrize("operation", OPERATIONS)
def test_default_plus_sections_is_exactly_the_full_rendering(operation):
    full = d.help_payload(operation, permitted=True, full=True)
    default = d.help_payload(operation, permitted=True)
    assert _reconstruct(operation, default) == full, "nothing is lost: every moved value is one exact section read away"
    sections = (default.get("sections") or {}).get("chars", {})
    for name, chars in sections.items():
        read = d.help_payload(operation, permitted=True, section=name)
        assert read["value"] == full[name] and read["chars"] == chars == len(json.dumps(full[name], ensure_ascii=False, default=str))
        assert json.loads(json.dumps(read["value"], ensure_ascii=False)) == full[name], "non-ASCII text round-trips"
    for name in d.HELP_REFERENCE_SECTIONS:
        assert name not in default, name
    # what a caller needs to act stays in the default
    for key in ("operation", "permitted", "verb", "concept", "does", "effects", "example", "native"):
        assert default[key] == full[key], key
    for key in ("rules", "expected", "variants", "errors", "recoverable_errors", "navigation_reads", "source_write_recipe", "header", "turn_bound"):
        assert default.get(key) == full.get(key), key
    if "input_summary" in default:
        summary = default["input_summary"]
        schema = full["input"]
        def check(schema, summary):
            if not isinstance(schema, dict) or not isinstance(summary, dict):
                return
            assert summary.get("required", []) == schema.get("required", []), "required fields stay in the default"
            if "properties" in schema:
                assert set(summary.get("fields", {})) == set(schema["properties"]), "every field is named"
                for name, prop in schema["properties"].items():
                    if isinstance(prop, dict) and "enum" in prop and isinstance(summary["fields"], dict):
                        assert summary["fields"][name] == {"enum": prop["enum"]}, "selector values stay in the default"
            for axis in ("oneOf", "anyOf", "allOf"):
                if axis in schema:
                    assert len(summary[axis]) == len(schema[axis])
                    for alternative, row in zip(schema[axis], summary[axis]):
                        check(alternative, row)
        check(schema, summary)


def test_the_held_cap_and_the_raw_sizes_are_measured_over_the_served_default():
    contract = writing_operating.tool_contract()
    permitted = set(contract["role_permissions"]["work"])
    chars = utf8 = full_chars = 0
    for operation in OPERATIONS:
        envelope = {"schema_version": writing_operating.VERSION, "digest": contract["digest"], "requested_operation": operation,
                    "action": d.help_payload(operation, permitted=operation in permitted)}
        text = json.dumps(envelope, ensure_ascii=False, default=str)
        chars += len(text); utf8 += len(text.encode("utf-8"))
        full_chars += len(json.dumps({**envelope, "action": d.help_payload(operation, permitted=operation in permitted, full=True)}, ensure_ascii=False, default=str))
    assert chars < 220767, chars
    assert utf8 < 220767 + 64, utf8          # the default is (almost) ASCII; bytes are measured, not assumed
    assert full_chars > 300000, 'the complete rendering is still what it was: nothing was deleted'


def test_native_section_reads_and_their_refusals(tmp_path):
    read = tools.execute(tmp_path, "p", "work", "help", {"operation": "source", "section": "raw_source_protocol"})
    assert read["action"]["value"] == d.help_payload("source", permitted=True, full=True)["raw_source_protocol"]
    with pytest.raises(ValueError, match="has no section 'binding_contract'; its sections: raw_source_protocol"):
        tools.execute(tmp_path, "p", "work", "help", {"operation": "source", "section": "binding_contract"})
    for bad in ({"section": "input"}, {"operation": "source", "section": "nonsense"}, {"concept": "argument@plan", "section": "input"},
                {"door": "http", "section": "input"}, {"operation": "source", "section": ""}):
        with pytest.raises(ValueError):
            tools.execute(tmp_path, "p", "work", "help", bad)
    variant = tools.execute(tmp_path, "p", "work", "help", {"operation": "concept_change", "variant": "add_node", "section": "input"})
    assert variant["action"]["variant"] == "add_node" and variant["action"]["value"]["properties"]["operation"]["const"] == "add_node"
    # a role without the operation's permission still reads its help; the default says so
    review = tools.execute(tmp_path, "p", "review", "help", {"operation": "structure_change"})["action"]
    assert review["permitted"] is False and "sections" in review


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "contract").mkdir(); (tmp_path / "proj").mkdir()
    (tmp_path / "proj/main.tex").write_text("exact source unchanged\n")
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{"name": "p", "kind": "project", "project_dir": "proj"}]}))
    monkeypatch.setattr(a, "_root", lambda: tmp_path)
    return tmp_path


def test_http_help_serves_the_same_section_and_refuses_the_same_shapes(project):
    def get(**fields):
        code, _, body = a.handle("/authoring/help", parse_qs(urlencode(fields), keep_blank_values=True), "GET", b"")
        return code, json.loads(body)
    code, body = get(project="p", mode="work", operation="structure", section="binding_contract")
    assert code == 200 and body["help"]["action"]["value"] == d.help_payload("structure", permitted=True, full=True)["binding_contract"]
    for fields in ({"section": "input"}, {"operation": "structure", "section": "nope"}, {"operation": "structure", "section": ""}):
        code, refused = get(project="p", mode="work", **fields)
        assert code >= 400 and "error" in refused, fields
    # an ambiguous selector (a repeated field) is refused by name, never resolved to one of its values
    for query, field in (("section=input&section=acts", "section"), ("operation=source&section=input", "operation")):
        code, _, body = a.handle("/authoring/help", parse_qs("project=p&mode=work&operation=structure&" + query, keep_blank_values=True), "GET", b"")
        assert code == 409 and json.loads(body)["error"] == "Help query fields must occur exactly once: " + field
    assert d.http_help("/authoring/help", "GET")["input"]["properties"]["section"]["enum"] == list(d.HELP_SECTIONS)
    assert a.handle("/authoring/help", parse_qs(urlencode({"project": "p", "mode": "work", "operation": "structure", "section": "input"})), "POST", b"{}")[0] >= 400


def test_section_values_keep_escapes_and_non_ascii_exactly_natively_and_over_http(project, tmp_path):
    """A moved value is returned byte-for-byte: TeX backslashes, quotes and non-ASCII text survive the section read,
    and `chars` counts characters (the cap's unit), not UTF-8 bytes."""
    full = d.help_payload("repository", permitted=True, full=True)["action_units"]
    text = json.dumps(full, ensure_ascii=False)
    assert "\u2013" in text and '\\"' in text, "the witness section carries an en dash and escaped quotes"
    native = tools.execute(tmp_path, "p", "work", "help", {"operation": "repository", "section": "action_units"})["action"]
    code, _, body = a.handle("/authoring/help", parse_qs(urlencode({"project": "p", "mode": "work", "operation": "repository", "section": "action_units"})), "GET", b"")
    served = json.loads(body.decode("utf-8"))["help"]["action"]
    assert code == 200 and native["value"] == served["value"] == full
    assert native["chars"] == len(text) < len(text.encode("utf-8")), "characters, not bytes"
    # the packer itself, over CJK, quotes, backslashes and control escapes
    value = {"examples": [{"note": "中文の説明 \\section{x} \"quoted\" tab\tnewline\n"}]}
    packed = d.help_section("source", "examples", value)
    assert packed["value"] == value["examples"] and packed["chars"] == len(json.dumps(value["examples"], ensure_ascii=False))
    assert json.loads(json.dumps(packed, ensure_ascii=False)) == packed


def test_section_admission_is_the_same_owner_schema_natively_and_over_http(project, tmp_path):
    """The section selector is admitted by the one declared help schema on both doors: a wrong type, a section without
    an operation, and an undeclared section are refused natively and over HTTP; nothing else is read."""
    for payload in ({"operation": "source", "section": 7}, {"section": "examples"}, {"operation": "source", "section": "not-declared"}):
        with pytest.raises(ValueError):
            tools.execute(tmp_path, "p", "work", "help", payload)
    for query in ({"operation": "source", "section": "not-declared"}, {"section": "examples"}):
        code, _, body = a.handle("/authoring/help", parse_qs(urlencode({"project": "p", "mode": "work", **query})), "GET", b"")
        assert code == 409 and "error" in json.loads(body), query
    schema = d.http_help("/authoring/help", "GET")["input"]
    assert schema["dependentRequired"]["section"] == ["operation"]
