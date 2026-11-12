"""deterministic.py - two offline encoders with no model, no network and no randomness.

These exist so the unit suite exercises cache, span and descent mechanics in milliseconds, and
so determinism tests have a geometry that cannot drift under an ONNX version. Neither is a
routing fallback: a hashing encoder has no semantics and is worse than lexical matching, and
saying so here is the point - a silent fallback to one would look like retrieval working.

Both port an IDEA from the laplace engine, re-implemented in atlas-clean code (the seal carries
no code, only agreement):

  HashEncoder      - character 3-gram sha1 hashing into a small unit sphere. Origin:
                     ``src/laplace/embed_router.py:175`` (``HashBackend``, "hash:3gram-256").
  SyntheticEncoder - four keyword families on orthogonal axes plus deterministic jitter, so a
                     synthetic corpus has real cluster structure to descend. Origin:
                     ``scripts/recursive_read_harness.py:131`` (``SyntheticBackend``).

The vectors are NOT byte-identical to the originals and are not meant to be: the laplace
backends are their own generation and this is another. What is ported is the construction.
"""

from __future__ import annotations

import hashlib

from .base import EncoderSpec, unit


def _logical_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


class HashEncoder:
    """Deterministic char-3gram hashing. No semantics; never a routing fallback."""

    encoder_id = "atlas-hash/3gram-256/1"
    dim = 256
    max_tokens = 512
    spec = EncoderSpec(
        encoder_id,
        _logical_digest("atlas-hash/3gram-256/1:sha1-character-trigrams"),
        _logical_digest("atlas-hash/3gram-256/1:unicode-codepoint-window"),
        "hashed-count/1",
        dim,
        "l2-unit-except-zero/1",
        "",
        "",
        "exact-component-equality/1",
        0.0,
    )

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        low = text.lower()
        for i in range(max(0, len(low) - 2)):
            digest = hashlib.sha1(low[i:i + 3].encode("utf-8")).digest()[:4]
            vec[int.from_bytes(digest, "big") % self.dim] += 1.0
        return unit(vec)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def query(self, text: str) -> list[float]:
        return self._vec(text)


class SyntheticEncoder:
    """Four keyword families on orthogonal axes plus deterministic jitter."""

    encoder_id = "atlas-synthetic/families-12/1"
    dim = 12
    max_tokens = 512
    FAMILIES = ("alpha", "beta", "gamma", "delta")
    spec = EncoderSpec(
        encoder_id,
        _logical_digest("atlas-synthetic/families-12/1:orthogonal-family-jitter"),
        _logical_digest("atlas-synthetic/families-12/1:lowercase-substring-membership"),
        "family-axis-plus-deterministic-jitter/1",
        dim,
        "l2-unit-except-zero/1",
        "",
        "",
        "exact-component-equality/1",
        0.0,
    )

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        family = 0
        for i, key in enumerate(self.FAMILIES):
            if key in text:
                family, vec[i] = i, 1.0
                break
        seed = int(hashlib.sha1(text.encode("utf-8")).hexdigest(), 16)
        for off in range(4):
            vec[4 + ((family * 2 + off) % 8)] += ((seed >> (off * 8)) % 100) / 400.0
        return unit(vec)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def query(self, text: str) -> list[float]:
        return self._vec(text)
