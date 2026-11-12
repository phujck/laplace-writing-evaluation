"""A static import check must never certify files outside its declared package."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def checker(tmp_path):
    source = Path(__file__).parents[1] / "scripts/distil.py"
    spec = importlib.util.spec_from_file_location("distil_reachable_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = str(tmp_path)
    package = tmp_path / "src" / "example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "door.py").write_text("from . import used\n")
    (package / "used.py").write_text("VALUE = 1\n")
    (package / "unused.py").write_text("VALUE = 2\n")
    return module


@pytest.mark.parametrize("files,status,summary", [
    (["src/example/used.py"], 0, "1 of 1"),
    (["src/example/unused.py"], 1, "0 of 1"),
    (["src/another/owner.py"], 1, "0 of 1"),
    (["src/example/used.py", "src/another/owner.py"], 1, "1 of 2"),
    (["src/example/missing.py"], 1, "0 of 1"),
])
def test_requested_files_are_counted_only_when_reached(checker, capsys, files, status, summary):
    args = SimpleNamespace(package="src/example", root="src/example/door.py", files=files)
    assert checker.cmd_reachable(args) == status
    output = capsys.readouterr().out
    assert f"reachable: {summary} reachable" in output
    if any(path not in ("src/example/used.py", "src/example/unused.py") for path in files):
        assert "NOT CHECKED" in output
        assert "--package and --root" in output
        assert "1 not checked" in output


def test_wrong_root_refuses_without_certifying_targets(checker, capsys):
    args = SimpleNamespace(package="src/example", root="src/another/door.py",
                           files=["src/example/used.py"])
    assert checker.cmd_reachable(args) == 2
    captured = capsys.readouterr()
    assert "not a file of package" in captured.err
    assert "reachable:" not in captured.out
