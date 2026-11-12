#!/usr/bin/env python3
"""Durable CLI for the DETECTOR-ORGANS runner (ARMING_2026-07-16, THE
INFRASTRUCTURE LAW: hand-production is BANNED — the runner is a committed organ,
not a scratchpad script). Rerunning re-mints the census:

    python3 scripts/run_detector_organs.py --project paper_falqon

Delegates to :func:`laplace.pipeline.detector_organs.main` (the organ), which fires
promise_audit + source_delta + meta_leak_scrub + gap_ledger read-only and banks
``<project>/rounds/detector_organs_<date>.json``."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from laplace.pipeline.detector_organs import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
