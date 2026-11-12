"""fold_oracle.py - A.34's member-by-member Python fold, as an INDEPENDENT TEST ORACLE.

The production fold (``src/atlas/grading/face.py``'s ``leaf_face``/``fold_faces``) and the
per-node path that called it (``grading/node.py``) were DELETED by packet J2-INTEGRATION: once
``atlas.front`` batches the reduction over a whole frontier, the per-node fold has no production
consumer, and ``face.py``'s own docstring named that as the condition for its deletion.

The EQUALITY PROOF still has to be runnable, so the fold lives on here - in the tests, not in
the system - as the control the range reductions are compared against. Being a re-statement of
A.34's rules rather than an import of the deleted code makes it a BETTER control: it cannot be
"fixed" by a change to the reduction it is supposed to check.

  SCALAR  the sorted set of distinct member values; it SURVIVES iff that set is a singleton.
  SET     the sorted union.
  DATE    the interval [lo, hi]; a leaf date is [d, d] and the fold is the hull.
  KIND    the counts map; a leaf kind is {k: 1} and the fold sums counts.

Complexity: O(total carrier entries), one pass.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

CARRIER_OF_TYPE = {"dict_utf8": "scalar", "enum": "kind", "date": "date", "timestamp": "date",
                   "span_ref": "set", "int64": "scalar", "bool": "kind"}


def leaf_face(fields: Mapping[str, Any], types: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """The face of ONE row: every declared field as its carrier's degenerate value."""
    face: dict[str, dict[str, Any]] = {}
    for name, arrow_type in sorted(types.items()):
        carrier = CARRIER_OF_TYPE[arrow_type]
        value = fields.get(name)
        if value is None:
            face[name] = {"carrier": carrier, "null": True}
            continue
        text = value if isinstance(value, str) else str(value)
        if carrier == "scalar":
            face[name] = {"carrier": "scalar", "values": [text]}
        elif carrier == "set":
            items = (sorted({str(v) for v in value})
                     if isinstance(value, (list, tuple, set)) else [text])
            face[name] = {"carrier": "set", "values": items}
        elif carrier == "date":
            face[name] = {"carrier": "date", "lo": text, "hi": text}
        else:
            face[name] = {"carrier": "kind", "counts": {text: 1}}
    return face


def _merge(name: str, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    if left["carrier"] != right["carrier"]:
        raise ValueError(f"FACE-FIELD-KIND-CONFLICT: {name}")
    carrier = left["carrier"]
    if left.get("null") and right.get("null"):
        return {"carrier": carrier, "null": True}
    if left.get("null"):
        return dict(right)
    if right.get("null"):
        return dict(left)
    if carrier in ("scalar", "set"):
        return {"carrier": carrier, "values": sorted(set(left["values"]) | set(right["values"]))}
    if carrier == "date":
        return {"carrier": "date", "lo": min(left["lo"], right["lo"]),
                "hi": max(left["hi"], right["hi"])}
    counts = dict(left["counts"])
    for key, value in right["counts"].items():
        counts[key] = counts.get(key, 0) + value
    return {"carrier": "kind", "counts": dict(sorted(counts.items()))}


def fold_faces(faces: Iterable[Mapping[str, Mapping[str, Any]]]
               ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """A.34's one fold. Returns (folded face, the named drops)."""
    faces = list(faces)
    if not faces:
        raise ValueError("EMPTY-FOLD")
    declared: dict[str, set[int]] = {}
    folded: dict[str, dict[str, Any]] = {}
    for index, face in enumerate(faces):
        for name, carrier in face.items():
            declared.setdefault(name, set()).add(index)
            folded[name] = (dict(carrier) if name not in folded
                            else _merge(name, folded[name], dict(carrier)))
    folded = dict(sorted(folded.items()))
    scalar_drops = [{"field": name, "disagreeing_member_values": carrier["values"]}
                    for name, carrier in folded.items()
                    if carrier["carrier"] == "scalar" and len(carrier.get("values", [])) > 1]
    partial = sorted(name for name, owners in declared.items() if len(owners) < len(faces))
    return folded, {"scalar_fields_that_did_not_survive": scalar_drops,
                    "fields_not_declared_by_all_members": partial,
                    "members_folded": len(faces)}


def scalar_survivors(face: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """The scalar fields that SURVIVED the fold: exactly the singletons."""
    return {name: carrier["values"][0] for name, carrier in face.items()
            if carrier["carrier"] == "scalar" and len(carrier.get("values", [])) == 1}


def fold_is_closed(faces: list[Mapping[str, Mapping[str, Any]]], split: int) -> bool:
    """fold(fold(first), fold(rest)) == fold(all), byte for byte."""
    left, _ = fold_faces(faces[:split])
    right, _ = fold_faces(faces[split:])
    through, _ = fold_faces([left, right])
    direct, _ = fold_faces(faces)
    return through == direct
