"""RESEARCH CONTEXT (core consolidation, research family R1): where a project's Research state lives.

The one explicit-root resolution of a project's Research home, for every Research owner and consumer:

  repo_root            the serving checkout (laplace.core.checkout.repo_root; the same resolution the runtime owners use)
  project(name, root)  the registry item and the project's STATE HOME, or (None, None) when this owner does not
                       serve the project. The home is the project-owned state directory
                       (manuscript_source.project_state_dir), not the selected draft's folder, so adding or
                       selecting a manuscript keeps the same Research home, result, figure and run identities;
                       a legacy registry row whose manuscript_dir is not on disk keeps the on-disk local
                       ``manuscript`` fallback until that layout is separately adjudicated.
  owner_home           the capability projection's question (writing_projects._capabilities): a project shows
                       Research exactly when this owner admits it.
  project_root         the registry project's own directory (scope=project), or None without one.
  inside               the one path fence (writing_portability.scoped_path): a path under a base, or None.

Nothing here reads records, runs or catalogues; those owners import this module and never the HTTP facade.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from laplace.core import checkout


def repo_root() -> Path:
    return checkout.repo_root()


def project(name: str, root: Path) -> tuple[Any, Path] | tuple[None, None]:
    from laplace.pipeline import registry
    item = registry.resolve(name, root)
    if item is None or not item.manuscript_dir:
        return None, None
    from laplace.manuscript import manuscript_source
    resolved = manuscript_source.resolve(name, repo_root=root)
    chosen = manuscript_source.project_state_dir(resolved, root)  # project-owned state home, not the selected draft's folder
    path = ((root / chosen) if isinstance(chosen, str) and not Path(chosen).is_absolute()
            else Path(chosen) if isinstance(chosen, str) else item.path(item.manuscript_dir, root))
    if path is None:
        return None, None
    # Legacy registry rows may carry manuscript_dir outside Project's normalized
    # conceptric convention; honor the on-disk local manuscript in that case.
    if not path.is_dir() and (root / 'manuscript').is_dir():
        path = root / 'manuscript'
    return item, path.resolve()


def owner_home(name: str, root: Path | None = None) -> Path | None:
    """The directory this Research owner serves `name` from, or None when it does not serve it
    (campaign research visibility, 2026-10-14)."""
    root = Path(root or repo_root()).resolve()
    try:
        return project(name, root)[1]
    except (OSError, ValueError):
        return None


def project_root(item: Any, root: Path) -> Path | None:
    if not getattr(item, 'project_dir', ''):
        return None
    return item.path(item.project_dir, root).resolve()


def inside(base: Path, candidate: str | Path) -> Path | None:
    from laplace.projects.writing_portability import scoped_path
    return scoped_path(base, candidate)
