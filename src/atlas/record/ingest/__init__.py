"""atlas.record.ingest - rung (a) for the three datasets this packet ingests.

Rung (a) only (B.7): structure parsed from the source container's own grammar by a parser with
no learned parameter, no model, no statistics and - the packet's own bar - no embedding computed
anywhere. Each module here declares its dataset (B.5), admits its blobs, mints its spans, rows,
relations and anchors, and returns one ``Ingestion``.

What each module additionally owes, and states in its own docstring, is what rung (a) CANNOT
extract from its dataset. That statement is not a caveat; it is the input to the measurement
that decides whether rung (b) is built at all (B.10).
"""

from __future__ import annotations

__all__ = ["toy", "longmem", "engine_rows"]
