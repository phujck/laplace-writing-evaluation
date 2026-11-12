"""Provider fixtures must use retained, process-isolated pytest scratch."""
from __future__ import annotations

from pathlib import Path


def test_default_scratch_has_no_checkout_instructions(tmp_path, request):
    from laplace.writing import operating as writing_operating

    # An explicitly requested --basetemp belongs to the caller. The ordinary
    # invocation must not manufacture a permanent run directory in the checkout.
    if request.config.option.basetemp is None:
        assert not tmp_path.is_relative_to(Path(request.config.rootpath))
        assert any(p.name.startswith("pytest-") for p in tmp_path.parents)
    assert not writing_operating._undeclared_instructions(tmp_path)


def test_default_scratch_keeps_pytest_retention_enabled(request):
    # Pytest ignores both retention settings when a plugin forces basetemp.
    # This catches the old plugin even if its destination is moved to /tmp.
    assert not request.config.pluginmanager.hasplugin("laplace.pytest_isolation")
    assert int(request.config.getini("tmp_path_retention_count")) == 1
    assert request.config.getini("tmp_path_retention_policy") == "failed"
