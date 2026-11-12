"""The wake, run through scripts/laplace-python without MCP or environment installation.

Bootstrap mirrors ``reconstruct_node.py``; the logic lives in ``laplace.engine.wake`` (the one
module the console script ``laplace-wake`` also enters). Runtime selection belongs to
this checkout's runtime_profiles.toml; LAPLACE_PYTHON can explicitly select its package
interpreter for a cold checkout. Source always belongs to this Laplace checkout.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "src"))

from laplace.core.runtime import require_system_runtime  # noqa: E402

require_system_runtime(ROOT)

# Runtime binding is deliberately not a bootstrap import side effect. ``laplace.engine.wake`` first
# reconstructs the canonical recipient frontier, then attempts a fail-closed binding and serves
# the resulting watcher state in the first payload field.  Import-time activation was able to
# resurrect retired occupants before projection migration or checkpoint reconciliation.

# If a dependency is missing under the declared system runtime, the projects shard rides blind
# under a REGISTRY DOWN banner that names the missing module but not the cure. Name the
# cure here, once, on stderr, beside it. Two modules, because one does not cover it:
# `registry` is the import self_corpus names, and it imports clean even with filelock
# gone (the historical culprit) -- filelock is reached lazily, from `pipeline.ledger`,
# only once the shard CALLS project_states. Importing both is the same work the wake is
# about to do anyway and costs ~75ms.
try:
    import laplace.pipeline.ledger  # noqa: F401
    import laplace.pipeline.registry  # noqa: F401
except ImportError as _exc:  # pragma: no cover - the degraded path
    print(
        f"REGISTRY DOWN incoming ({_exc}) -- this interpreter ({sys.executable}) is missing "
            "the project's dependencies. Provision the selected runtime explicitly; wake never installs.",
        file=sys.stderr,
    )
except Exception:  # noqa: BLE001 - a non-import failure is the wake's own to report
    pass

from laplace.engine.wake import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
