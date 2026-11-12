"""Declaration coordinates resolve from package files while retaining public paths."""
from __future__ import annotations

from pathlib import Path

import pytest

from laplace.native import declarations


def _sites() -> set[str]:
    sites = {declaration.handler for declaration in declarations.HTTP_DECLARATIONS.values()}
    for declaration in declarations.HTTP_DECLARATIONS.values():
        sites.update(declaration.resolved_consumers().values())
        sites.update(declaration.resolved_responses().values())
    return sites


def test_all_declaration_coordinates_are_packaged_but_remain_logical():
    package = Path(declarations.__file__).resolve().parents[1]   # the laplace package (declarations lives in laplace/native)
    logical = {declarations.TOOL_DOOR, *(site.rpartition(":")[0] for site in _sites())}
    assert logical
    for rel in logical:
        assert rel.startswith("src/laplace/")
        source = declarations._serving_source(rel)
        assert source.is_file() and source.is_relative_to(package)
        assert source == package / Path(rel).relative_to("src/laplace")
    assert declarations.dispatch_site("help").startswith("src/laplace/native/tools.py:")


def test_declaration_source_resolver_refuses_nonpackage_coordinates():
    with pytest.raises(ValueError, match="outside the executing laplace package"):
        declarations._serving_source("tools/writing_verbs/http_routes.csv")
    with pytest.raises(ValueError, match="escapes the executing laplace package"):
        declarations._serving_source("src/laplace/../outside.py")
