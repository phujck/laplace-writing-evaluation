"""The standing cold-probe instrument (banked from the 2026-07-13 cold-wake audit): a graded
question list + a pure scorer, so every close mechanically re-asks *could a stranger wake from
this?* instead of that being a one-off audit someone has to remember to run.

Three pure functions, no I/O beyond reading the question file: ``load_questions`` parses the
markdown table in ``holdout/COLD_WAKE_QUESTIONS.md``; ``resolve`` walks a dotted path (with one
list-selector form) into a reconstructed payload; ``score_coverage`` answers, for a payload of a
given grade, which of that grade's questions the payload actually covers."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_ROW_RE = re.compile(r"^\|\s*(?P<id>[^|]+?)\s*\|\s*(?P<question>[^|]+?)\s*\|\s*(?P<grade>[^|]+?)\s*\|\s*(?P<answers>[^|]+?)\s*\|\s*$")
_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")
_LIST_SEL_RE = re.compile(r"^(?P<key>[^\[\]]+)\[(?P<field>[^=\]]+)=(?P<value>[^\]]+)\]$")


def load_questions(md_path: Path) -> list[dict]:
    """Parse the ``| id | question | grade | answers |`` table. ``grade`` becomes an int;
    ``answers`` becomes a list of ``;``-separated terms (dotted paths and/or ``regex:...``)."""
    rows: list[dict] = []
    header_seen = False
    for line in Path(md_path).read_text(encoding="utf-8").splitlines():
        m = _ROW_RE.match(line.strip())
        if not m:
            continue
        if _SEP_RE.match(line.strip()):
            continue
        if not header_seen:
            # the header row itself matches the row shape; skip it, then everything after is data
            header_seen = True
            continue
        answers = [a.strip() for a in m.group("answers").split(";") if a.strip()]
        rows.append({
            "id": m.group("id").strip(),
            "question": m.group("question").strip(),
            "grade": int(m.group("grade").strip()),
            "answers": answers,
        })
    return rows


def resolve(payload: dict, path: str) -> Any:
    """Dotted-path resolution with one list form: ``shards[shard=wants].body`` means: in the
    list at key ``shards``, take the first dict whose ``shard`` field equals ``wants``, then
    descend ``.body``. Missing anything along the way resolves to None."""
    cur: Any = payload
    for part in path.split("."):
        if cur is None:
            return None
        m = _LIST_SEL_RE.match(part)
        if m:
            key, field, value = m.group("key"), m.group("field"), m.group("value")
            if not isinstance(cur, dict) or key not in cur:
                return None
            items = cur[key]
            if not isinstance(items, list):
                return None
            match = next((it for it in items if isinstance(it, dict) and it.get(field) == value), None)
            if match is None:
                return None
            cur = match
        else:
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
    return cur


def _term_matches(payload: dict, term: str) -> bool:
    if term.startswith("regex:"):
        pattern = term[len("regex:"):]
        return re.search(pattern, json.dumps(payload, ensure_ascii=False)) is not None
    value = resolve(payload, term)
    if value is None:
        return False
    if isinstance(value, (str, list, dict)) and not value:
        return False
    return True


def score_coverage(payload: dict, rows: list[dict]) -> dict:
    """Score a reconstructed ``payload`` against its own grade's rows: a row is ANSWERED iff any
    of its answers-terms resolves non-empty. Rows for a different grade than ``payload["grade"]``
    are SKIPPED (each grade is scored only against its own grade's payload)."""
    payload_grade = payload.get("grade")
    answered: list[str] = []
    residue: list[str] = []
    skipped: list[str] = []
    for row in rows:
        if row["grade"] != payload_grade:
            skipped.append(row["id"])
            continue
        if any(_term_matches(payload, term) for term in row["answers"]):
            answered.append(row["id"])
        else:
            residue.append(row["id"])
    return {"answered": answered, "residue": residue, "skipped": skipped}
