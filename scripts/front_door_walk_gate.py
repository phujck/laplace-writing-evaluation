#!/usr/bin/env python3
# ruff: noqa: I001
"""Cold bootstrap for the typed CAMP-R3 author-walk gate."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.core.runtime import require_system_runtime  # noqa: E402

require_system_runtime(ROOT)

from laplace.manuscript.walk_verdicts import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
