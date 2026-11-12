"""Reading an append-only JSONL store: every JSON object on its own line.

A store is append-only free text at heart: a torn final write or a hand edit leaves a bad line, and a reader
that halts on one goes dark exactly when it is needed. So a line that does not decode, or decodes to anything
but an object, is skipped and counted, never raised. Blank lines are neither rows nor malformed.
"""
from __future__ import annotations

import json
from pathlib import Path


def decode_row(raw: str | bytes) -> dict | None:
    """One line as a row: the JSON object it holds, or None when it does not decode or is not an object."""
    try:
        row = json.loads(raw)
    except (ValueError, UnicodeError):
        return None
    return row if isinstance(row, dict) else None


def read_rows(path: Path | str, *, errors: str = "strict") -> tuple[list[dict], int]:
    """(rows, malformed) for one store; a missing store is ([], 0). ``errors`` is the text decoding policy."""
    p = Path(path)
    if not p.exists():
        return [], 0
    rows: list[dict] = []
    malformed = 0
    for line in p.read_text(encoding="utf-8", errors=errors).splitlines():
        line = line.strip()
        if not line:
            continue
        row = decode_row(line)
        if row is None:
            malformed += 1
        else:
            rows.append(row)
    return rows, malformed


def load_records(path: Path | str) -> list[dict]:
    """Every JSON object in a store, malformed lines skipped."""
    return read_rows(path)[0]
