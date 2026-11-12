"""device_policy.py - a fallback is a decision that leaves a row, never a default that
leaves silence.

His ruling (2026-08-21, in-session, after the chi bench was caught contemplating a numpy
fallback on a machine whose GPU took the production fold the day before): no organ
degrades quietly. Every backend choice that lands on the CPU for a non-dialed reason is
recorded as a typed row in ``.fallback_events.jsonl`` and printed loudly; with
``LAPLACE_REQUIRE_GPU`` set, an undialed CPU landing is a named refusal instead. Dialed
choices (an explicit deny flag, a caller override) are recorded too, marked ``dialed`` -
visible and lawful. The recorder itself is best-effort: a logging failure never takes
down the organ it watches. (WO-20260821-environment-persistence-failure, leg 3.)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

REQUIRE_FLAG = "LAPLACE_REQUIRE_GPU"
LOG_FILE = ".fallback_events.jsonl"
LOG_OVERRIDE = "LAPLACE_FALLBACK_LOG"   # absolute path; the test-isolation door (see _log_path)


class DeviceRequired(BaseException):
    """A GPU-required deposit refusal, deliberately outside ``Exception``.

    The keeper's additive meaning-middle boundary catches ordinary ``Exception``
    values and degrades to the folder middle. A device refusal is not an ordinary
    missing capability and must cross that boundary to stop the deposit before it
    can publish a CPU-derived fold.
    """


def _log_path() -> Path:
    """Where the row lands. ``LAPLACE_FALLBACK_LOG`` (an absolute path) wins outright; otherwise
    ``LAPLACE_ROOT``/``.fallback_events.jsonl`` as before.

    THE OVERRIDE EXISTS BECAUSE THE STORE WAS BEING FORGED BY ITS OWN TEST SUITE (census
    2026-08-21, finding C4). ``tests/test_metric_distill.py`` (4 rows/run) and
    ``tests/test_meaning_upfold_incremental.py`` (1 row/run) set no ``LAPLACE_ROOT``, so every
    suite run appended UNDIALED CPU landings to the repo's real ``.fallback_events.jsonl`` - 72 of
    its first 95 rows, describing monkeypatched fixtures rather than this box. A census store that
    its own tests write into cannot answer "how often do we fall back", which is the only question
    it exists for. ``tests/conftest.py`` now points this at ``tmp_path`` for every test, the same
    way ``LAPLACE_STATE`` is already isolated there."""
    override = (os.environ.get(LOG_OVERRIDE) or "").strip()
    if override:
        return Path(override)
    return Path(os.environ.get("LAPLACE_ROOT", ".")) / LOG_FILE


def _provenance() -> dict:
    """WHO PRODUCED THIS ROW - the census's missing column (2026-08-21, GPU_MIGRATION census
    finding C4). The store's first 95 rows carried ts/organ/choice/why/dialed and nothing else,
    so a row written by a unit test that MONKEYPATCHES cupy away was byte-shaped exactly like a
    row from a real deposit that lost the device. The census could only separate them by forensics
    (burst arity, the word "simulated" inside ``why``), and that forensics does not survive a
    message change. So the row now says where it came from: ``proc`` (argv[0] basename), ``pid``,
    and ``synthetic`` - True whenever pytest is the running program, because a test's device
    landing is a fixture, never evidence about this box. Additive only: every existing reader keys
    on organ/choice/dialed and is untouched."""
    proc = "python"
    try:
        import sys
        proc = os.path.basename(sys.argv[0]) or "python"
    except Exception:  # noqa: BLE001 - provenance is best-effort, like the rest of the recorder
        pass
    import sys as _sys
    return {"proc": proc, "pid": os.getpid(),
            "synthetic": "pytest" in _sys.modules or "PYTEST_CURRENT_TEST" in os.environ}


def record_fallback(organ: str, choice: str, why: str, *, dialed: bool = False) -> None:
    """Record a backend landing. CPU landings print loudly; undialed CPU landings raise
    under the require flag. GPU landings are not recorded (they are the ruled default).

    ``choice="disabled"`` IS NOT A DEVICE LANDING (census 2026-08-21, finding C5). Some organs
    degrade because a CPU-side capability is absent, not because the device is: ``_spectral_allowed``
    disables the spectral branch when scikit-learn/scipy are missing. Routed through the ``"cpu"``
    vocabulary, that produced a FALSE REFUSAL - measured under ``LAPLACE_REQUIRE_GPU`` on a
    GPU-perfect box, a missing scikit-learn raised ``DeviceRequired: ... the GPU is unavailable
    (scipy/sklearn missing)``. A wrong diagnosis that fires on healthy hardware is exactly what
    would have stopped the require flag becoming this box's default (WO-20260821-full-gpu-migration's
    endpoint). So ``disabled`` records and still prints loudly - it IS a degrade - but the GPU flag
    has no jurisdiction over it and never refuses."""
    if choice == "gpu":
        return
    row = {"ts": datetime.now(timezone.utc).isoformat(), "organ": organ,
           "choice": choice, "why": why, "dialed": dialed, **_provenance()}
    try:
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass
    if not dialed:
        # THE LINE NAMES THE FILE THE ROW ACTUALLY WENT INTO, not the default file name. Both
        # messages used to print the constant ``.fallback_events.jsonl`` while ``_log_path`` may
        # have sent the row anywhere ``LAPLACE_FALLBACK_LOG`` pointed - so the suite, and every
        # hand proof that redirects the store, was told to look in a file with nothing in it.
        # A claim names its own run (2026-08-21, the Enforce lane, caught in its own proof).
        where = _log_path()
        if choice == "disabled":
            print(f"DISABLED [{organ}]: {why} (a CPU-side capability is missing, not the device; "
                  f"row in {where})")
            return                                   # the GPU flag has no jurisdiction here
        print(f"FALLBACK [{organ}]: running on {choice} - {why} "
              f"(the GPU is the ruled home for this organ; row in {where})")
        if str(os.environ.get(REQUIRE_FLAG, "")).strip().lower() in {"1", "true", "yes", "on"}:
            raise DeviceRequired(f"{organ}: {REQUIRE_FLAG} is set and the GPU is "
                                 f"unavailable ({why}) - refusing rather than degrading")
