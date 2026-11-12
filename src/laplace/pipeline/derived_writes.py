"""derived_writes.py — the one gate on DERIVED-STATE writes into the LIVE repo.

Some pipeline organs refresh a *derived* file beside the thing it describes: the
form channel's per-(store, section) retrieval sidecar
(``stage_retrieval.write_form_channel_sidecar`` →
``_form_retrieval.<store>.<section>.json``) and the master node index
(``node_index.write_node_index`` → ``<manuscript>/node_index.json``). Both records
carry a WALL-CLOCK stamp (``ts`` / ``built_at``), so a refresh rewrites the file
even when nothing substantive moved.

That is harmless in a run. It is corrosive under **test**, because several tests
assert against the REAL repo state and reach these organs on the way
(``tests/test_essence_hygiene.py`` compiles a live narrative dispatch;
``tests/test_provenance_index.py`` mints the live index). A green pytest run then
DIRTIES the working tree with a timestamp-only diff, and every tree-state probe
after it reads a dirtier tree than the change under test — bisected live
2026-08-17 and reproduced five times since
(``corpus_friction/work_orders.jsonl`` WO-20260817-test-mutates-working-tree; the
AP-13 clause of AMEND-20260820-acceptance-probe-schema). Same defect class as the
audit's honest-skip rows: a green run that silently mutates state.

**The gate.** :func:`enabled` is the one predicate every such refresh asks before
touching the live tree.

  * **Outside pytest it is TRUE** — production behaviour is byte-identical to
    before this module existed. The gate is not a new permission a pipeline run
    has to be granted; a real run still banks its audit trail.
  * **Under pytest it is FALSE** — the read-only default the work order asked
    for. Detected through ``PYTEST_CURRENT_TEST``, the environment variable
    *pytest itself sets* per test, so this stays a plain env read (the repo's
    ``LAPLACE_NO_SPECTRAL`` / ``LAPLACE_UV_BIN`` idiom) rather than importing
    pytest or sniffing ``sys.modules`` from library code.
  * **:data:`WRITE_FLAG` overrides both directions** — a test that genuinely
    exercises the refresh sets it deliberately and is then responsible for what
    it lands (redirect the writer, or restore the bytes). "A write flag tests
    never pass" is the default; the two tests that DO pass it are the tests OF
    the writers, and each one either monkeypatches the write away from disk or
    restores the file it touched.

The gate is on the *refresh decision*, never on the persist primitive:
``write_form_channel_sidecar(path, record)`` and ``write_node_index(..., root)``
still write exactly where they are told when called directly (a ``tmp_path``
roundtrip test must keep working). What is gated is the organ deciding to refresh
LIVE derived state as a side effect of being read.
"""
from __future__ import annotations

import os

#: the explicit opt-in. Set it (to any non-empty value) to permit derived-state
#: refreshes even under pytest.
WRITE_FLAG = "LAPLACE_SIDECAR_WRITE"

#: the env var pytest sets for the duration of each test — the read-only tell.
#: Reading it keeps this an env check, not a test-framework import.
PYTEST_MARKER = "PYTEST_CURRENT_TEST"


def enabled(env: dict[str, str] | None = None) -> bool:
    """True when a derived-state refresh may touch the LIVE repo tree.

    ``env`` defaults to ``os.environ`` (injectable so the rule itself is
    testable without mutating the process)."""
    e = os.environ if env is None else env
    if e.get(WRITE_FLAG):
        return True                     # explicit opt-in wins everywhere
    return PYTEST_MARKER not in e       # read-only under pytest, live otherwise


def read_only_note(env: dict[str, str] | None = None) -> str | None:
    """A one-line reason when writes are OFF, else ``None`` — so a caller that
    wants to SAY it skipped can, rather than skipping silently."""
    if enabled(env):
        return None
    return (f"derived-state writes are read-only under pytest "
            f"(set {WRITE_FLAG}=1 to permit them)")
