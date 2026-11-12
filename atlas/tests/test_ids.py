"""test_ids.py - the hashing law: canonical JSON is order-free, and ids are clock-free."""

from __future__ import annotations

import pytest

from atlas.errors import NotCanonicalizable
from atlas.ids import HASH_PREFIX, canonical_json, chash, hash_bytes, hex_of


def test_canonical_json_sorts_keys_and_tightens_separators():
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert canonical_json([1, {"z": 0, "y": 0}]) == '[1,{"y":0,"z":0}]'


def test_canonical_json_is_insertion_order_free():
    one = {"a": 1, "b": {"c": 2, "d": 3}}
    two = {"b": {"d": 3, "c": 2}, "a": 1}
    assert canonical_json(one) == canonical_json(two)
    assert chash(one) == chash(two)


def test_canonical_json_keeps_non_ascii_unescaped():
    assert canonical_json({"k": "é"}) == '{"k":"é"}'


def test_chash_is_prefixed_and_stable():
    value = {"x": [1, 2, 3], "y": None}
    first = chash(value)
    assert first.startswith(HASH_PREFIX)
    assert len(hex_of(first)) == 64
    assert first == chash(value)


def test_chash_separates_distinct_values():
    assert chash({"a": 1}) != chash({"a": 2})
    assert chash({"a": 1}) != chash({"a": "1"})


def test_hash_bytes_is_over_raw_bytes():
    import hashlib
    data = b"the record is the memory"
    assert hash_bytes(data) == HASH_PREFIX + hashlib.sha256(data).hexdigest()


def test_hex_of_refuses_an_unprefixed_hash():
    with pytest.raises(NotCanonicalizable) as exc:
        hex_of("deadbeef")
    assert exc.value.reason == "id-not-canonicalizable"


def test_canonical_json_refuses_an_unencodable_value():
    with pytest.raises(NotCanonicalizable):
        canonical_json({"k": object()})
