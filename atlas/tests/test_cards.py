"""Exercise computed cards, bounded entry, and compile-only cold verb packets."""
import importlib.util
import ast
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest

from atlas import cards
from atlas.entry import BYTE_CAP, build_entry, card_page, encode_entry, get_card
from atlas.errors import StoreError


@pytest.fixture(scope="module")
def registry():
    return cards.compute_registry()


def test_residual_verb_cards_have_discovered_contract_or_typed_retirement(registry):
    for operation in ("read_atlas_object", "read_portable_authority_adoption",
                      "seal_portable_authority_adoption", "read_seat_mail_frontier"):
        card = get_card("verb:api:ConceptricStore." + operation)
        if operation == "read_seat_mail_frontier":
            assert card["issue"]["code"] == "CARD-VERB-RETIRES"
            assert card["issue"]["reason"] == "custody-era, retires with CR-20260914-custody-off"
            assert not any(i["code"] == "CARD-TEST-MISSING" and i.get("id") == card["id"]
                           for i in registry["issues"])
        else:
            assert card["test"] == "atlas/tests/test_store_projection.py"
            assert card["test_scope"] == "atlas.store.ConceptricStore." + operation
            tree = ast.parse((cards.ROOT / card["test"]).read_text())
            test = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                        and n.name == card["test_node"].split("::")[-1])
            assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                       and n.func.attr == operation for n in ast.walk(test))


def test_up_member_ref_constructor_round_trip_and_empty_address_refusal():
    from atlas.updown_history import UpMemberRef
    from atlas.errors import StateTransitionRefused
    member = UpMemberRef("object:child", "sha256:" + "a" * 64)
    assert UpMemberRef.from_dict(member.to_dict()) == member
    for object_id, content in (("", member.content_handle), (member.object_id, "")):
        with pytest.raises(StateTransitionRefused):
            UpMemberRef(object_id, content)


def test_up_member_ref_card_discovers_constructor_test(registry):
    card = get_card("structure:type:UpMemberRef")
    assert card["test"] == "atlas/tests/test_cards.py"
    assert card["test_node"].endswith("::test_up_member_ref_constructor_round_trip_and_empty_address_refusal")
    assert card["test_scope"] == "constructor:atlas.updown_history.UpMemberRef"


def test_refusal_cards_discover_asserted_reason_tests(registry):
    asserted = {}
    for path in cards._files(cards.CONTAINER / "tests"):
        if not path.name.startswith("test_"):
            continue
        for test in ast.walk(ast.parse(path.read_text())):
            if isinstance(test, ast.FunctionDef) and test.name.startswith("test_"):
                for node in ast.walk(test):
                    if isinstance(node, ast.Assert):
                        for value in ast.walk(node.test):
                            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                                asserted.setdefault(value.value, set()).add(
                                    cards._rel(path) + "::" + test.name)
    covered = []
    for card in registry["structure"]:
        if card["id"].startswith("structure:refusal:") and card["refusals"][0] in asserted:
            reason = card["refusals"][0]
            assert card["test_node"] in asserted[reason]
            assert card["test"] == card["test_node"].split("::")[0]
            assert card["test_scope"] == "reason:" + reason
            covered.append(card["id"])
    assert covered


def test_refusal_test_discovery_requires_assertion_not_reason_mention(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    probe = tests / "test_reason.py"
    probe.write_text('def test_probe():\n    reason = "stale-owner"\n')
    registry = cards.compute_registry(tests=tests)
    refusals = [c for c in registry["structure"] if c["id"].startswith("structure:refusal:")
                and c["refusals"] == ["stale-owner"]]
    assert refusals and all(c["test"] is None for c in refusals)
    probe.write_text('def test_probe():\n    assert caught.value.reason == "stale-owner"\n')
    registry = cards.compute_registry(tests=tests)
    assert all(c["test"] == cards._rel(probe) and c["test_node"].endswith("::test_probe")
               for c in registry["structure"] if c["id"] in {r["id"] for r in refusals})


def test_every_tool_has_card_or_typed_issue(registry):
    ids = {c["id"] for c in registry["verbs"]} | {i.get("id") for i in registry["issues"]}
    for path in cards._files(cards.PACKAGE / "tools"):
        if path.stem != "__init__":
            module = ".".join(path.relative_to(cards.PACKAGE).with_suffix("").parts)
            assert "verb:" + module in ids


def test_new_tool_is_discovered_without_registration_and_missing_face_is_loud(tmp_path):
    package = tmp_path / "atlas"
    (package / "tools").mkdir(parents=True)
    tests = tmp_path / "tests"
    tests.mkdir()
    for name in ("errors", "state", "store"):
        shutil.copyfile(cards.PACKAGE / (name + ".py"), package / (name + ".py"))
    new = package / "tools/new_verb.py"
    new.write_text('''"""Inspect a newly installed Atlas tool."""
import argparse
from atlas.errors import StoreError as Refusal
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    raise Refusal("missing")
raise RuntimeError("discovery must not execute a tool")
''')
    r = cards.compute_registry(package, tests)
    card = next(c for c in r["verbs"] if c["id"] == "verb:tools.new_verb")
    assert card["face"] == "Inspect a newly installed Atlas tool."
    assert card["refusals"] == ["store-error"]
    assert card["inputs"][0]["flags"] == ["--input"]
    new.write_text("def main():\n    pass\n")
    changed = cards.compute_registry(package, tests)
    assert not any(c["id"] == card["id"] for c in changed["verbs"])
    assert any(i["id"] == card["id"] and i["code"] == "CARD-FACE-MISSING"
               for i in changed["issues"] if "id" in i)
    new.write_text("def broken(\n")
    assert any(i["code"] == "CARD-SOURCE-UNREADABLE" and i["id"] == card["id"]
               for i in cards.compute_registry(package, tests)["issues"] if "id" in i)


def test_discovery_excludes_hidden_fixture_copies(tmp_path):
    hidden = tmp_path / ".other-worker-fixtures" / "tools"
    hidden.mkdir(parents=True)
    (hidden / "false_tool.py").write_text("raise RuntimeError('not source')")
    actual = tmp_path / "actual.py"
    actual.write_text("pass")
    assert list(cards._files(tmp_path)) == [actual]


def test_all_card_descents_resolve_to_exact_existing_sources(registry):
    assert "snapshot-incomplete" in get_card("verb:tools.export_verify")["refusals"]
    for card in registry["verbs"] + registry["structure"]:
        argv = shlex.split(card["descend"])
        assert argv[:4] == ["python", "-m", "atlas.entry", "--card"]
        reached = get_card(argv[4])
        assert reached == card
        source = cards.ROOT / reached["source"]["path"]
        assert source.is_file()
        assert 1 <= reached["source"]["line"] <= len(source.read_text().splitlines())
        assert 0 < len(card["face"]) <= 160
        assert len(encode_entry(card)) <= BYTE_CAP
        if card["test"]:
            assert (cards.ROOT / card["test"]).is_file()


def test_card_ids_stable_and_cached_results_are_not_mutable(registry):
    first = cards.compute_registry()
    second = cards.compute_registry()
    for field in ("verbs", "structure"):
        assert [c["id"] for c in first[field]] == [c["id"] for c in second[field]]
        assert len({c["id"] for c in first[field]}) == len(first[field])
    first["verbs"].clear()
    assert cards.compute_registry()["verbs"] == registry["verbs"]


def test_registry_cache_uses_content_digest_and_stat_fast_path(tmp_path, monkeypatch):
    package = tmp_path / "src" / "atlas"
    tests = tmp_path / "tests"
    ignored = shutil.ignore_patterns(".*", "__pycache__")
    shutil.copytree(cards.PACKAGE, package, ignore=ignored)
    tests.mkdir()
    first = cards.compute_registry(package, tests)
    cache_root = cards._cache_root(package, tests)
    first_records = sorted(cache_root.glob("registry-*.json"))
    assert len(first_records) == 1

    hashed = []
    original_hash = cards._sha256_file
    monkeypatch.setattr(cards, "_sha256_file",
                        lambda path: (hashed.append(path), original_hash(path))[1])
    original_compute = cards._compute_registry
    monkeypatch.setattr(cards, "_compute_registry",
                        lambda *args: (_ for _ in ()).throw(AssertionError("registry recomputed")))
    assert cards.compute_registry(package, tests) == first
    assert hashed == []

    changed = package / "errors.py"
    changed.write_text(changed.read_text() + "\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="registry recomputed"):
        cards.compute_registry(package, tests)
    assert hashed == [changed.resolve()]
    monkeypatch.setattr(cards, "_compute_registry", original_compute)
    assert cards.compute_registry(package, tests) == first
    assert len(list(cache_root.glob("registry-*.json"))) == 2


def test_entry_import_does_not_load_blueprint():
    proc = subprocess.run(
        ["/usr/bin/python3", "-c",
         "import sys; import atlas.entry; assert 'atlas.blueprint' not in sys.modules"],
        capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "src"})
    assert proc.returncode == 0, proc.stderr


def test_card_indexes_reach_every_id_and_reject_unknown(registry):
    for field in ("verbs", "structure"):
        seen, offset = [], 0
        while True:
            page = card_page(field, offset)
            assert len(encode_entry(page)) <= BYTE_CAP
            seen.extend(c["id"] for c in page["cards"])
            if page["next"] is None:
                break
            offset = int(shlex.split(page["next"])[-1])
        assert seen == [c["id"] for c in registry[field]]
    with pytest.raises(StoreError, match="card id does not resolve"):
        get_card("verb:missing")


def test_entry_with_cards_bounded_and_store_records_still_reachable(tmp_path):
    from test_updown_history import setup_store
    store, _, _ = setup_store(tmp_path / "store")
    page = build_entry(store.root)
    assert len(encode_entry(page)) <= page["byte_cap"] == BYTE_CAP
    assert page["verbs"] and page["structure"] and page["records"]
    for field in ("verbs", "structure"):
        omission = next(o for o in page["omissions"] if o["field"] == field)
        assert omission["descend"] == "python -m atlas.entry --card <id>"
        assert omission["index"] == f"python -m atlas.entry --cards {field}"


def cold_module():
    path = cards.ROOT / "scripts/atlas_cold_coverage.py"
    spec = importlib.util.spec_from_file_location("cold_coverage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verbs_compile_is_seeded_strict_and_never_dispatches_or_reads_snapshot(monkeypatch, capsys):
    cold = cold_module()
    def forbidden(*args, **kwargs):
        raise AssertionError("compile-only must not dispatch or read snapshots or write files")
    monkeypatch.setattr(cold, "latest_snapshot", forbidden)
    monkeypatch.setattr(cold.subprocess, "run", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    assert cold.main(["--mode", "verbs", "--k", "3", "--seed", "41", "--compile-only"]) == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["ids"] == cold.verbs_packet(3, 41)["ids"]
    assert len(packet["ids"]) == len(set(packet["ids"])) == 3
    assert packet["ids"] != cold.verbs_packet(3, 42)["ids"]
    def strict(schema):
        if isinstance(schema, dict):
            if schema.get("type") == "object":
                assert schema["additionalProperties"] is False
                assert set(schema["required"]) == set(schema["properties"])
            for value in schema.values():
                strict(value)
        elif isinstance(schema, list):
            for value in schema:
                strict(value)
    strict(packet["schema"])
    assert "run that test file" in packet["goal"]
    assert "CARD-TEST-MISSING" in packet["goal"]


def test_card_cli_needs_no_store(registry):
    for card in (registry["verbs"][0], registry["structure"][0]):
        proc = subprocess.run(["/usr/bin/python3", "-m", "atlas.entry", "--store", "/absent",
                               "--card", card["id"]], capture_output=True, text=True,
                              env={**os.environ, "PYTHONPATH": "src"}, check=True)
        assert json.loads(proc.stdout) == card


def test_verbs_measure_refuses_incomplete_duplicate_and_extra_fields():
    import jsonschema
    cold = cold_module()
    packet = cold.verbs_packet(1, 41)
    row = {"card_id": packet["ids"][0], "card_reached": False, "card_command": "",
           "test_path": "", "test_reached": False, "test_command": "", "exit_code": None,
           "test_output": "", "reads": 0, "issue": "CARD-NOT-REACHED"}
    answer = {"entry_used": "", "verbs": [row], "reads_total": 0,
              "enumerated_store_dirs": False, "blockers": []}
    assert cold.measure_verbs(answer, packet["ids"])["tests_reported_passed"] == 0
    answer["verbs"] = [row, row]
    with pytest.raises(ValueError, match="VERB-RETURN-IDS"):
        cold.measure_verbs(answer, packet["ids"])
    answer["verbs"] = []
    with pytest.raises(ValueError, match="VERB-RETURN-IDS"):
        cold.measure_verbs(answer, packet["ids"])
    answer["invented"] = True
    with pytest.raises(jsonschema.ValidationError):
        cold.measure_verbs(answer, packet["ids"])
