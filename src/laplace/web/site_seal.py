"""FROZEN (2026-07-08, the shelving): the remote review surface is shelved; this
crypto stays importable (any future static bundle reuses it) but gains no features.

The password gate for static bundles — the one producer of the scramble.

A static host serves whatever bytes it holds to anyone; a client-side "are you
allowed?" check is bypassed by opening the network tab. So to make a bundle "not
viewable without the password" (his ask, 2026-07-03 — a gate, not a fortress) the
bytes themselves are scrambled under the password: AES-GCM with a PBKDF2-derived key,
decrypted in-browser by WebCrypto. Plain password protection, no ceremony — the same
primitive WebCrypto exposes, so the browser half is a dozen lines.

This module is corpus/project-agnostic: it scrambles bytes. Any exporter going forward
uses it rather than re-inlining crypto (``export_review.py`` does; ``export_site.py``
keeps its own test-pinned copy and should migrate here when next touched).
"""
from __future__ import annotations

import base64
import secrets

# 200k PBKDF2 rounds: standard-strength for a password gate, and snappy enough that
# unlocking on a phone is well under a second. This is a draft behind a password, not
# a key-management system — the number is deliberately not theatrical.
PBKDF2_ITER = 200_000
_MAGIC = b"LREV1\0"          # bundle magic + version, so the app can sanity-check the blob


def derive_key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                      iterations=PBKDF2_ITER).derive(password.encode("utf-8"))


def encrypt(plain: bytes, password: str) -> bytes:
    """Scramble ``plain`` under ``password``. Layout: MAGIC ‖ salt(16) ‖ iv(12) ‖ ct.

    The MAGIC lets the browser reject a truncated/wrong file before deriving a key; the
    salt+iv ride inline so the bundle is a single self-describing blob."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    ct = AESGCM(derive_key(password, salt)).encrypt(iv, plain, None)
    return _MAGIC + salt + iv + ct


def decrypt(blob: bytes, password: str) -> bytes:
    """The Python mirror of the browser decrypt — used by tests to pin the round-trip."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if blob[:len(_MAGIC)] != _MAGIC:
        raise ValueError("not a laplace review bundle")
    body = blob[len(_MAGIC):]
    salt, iv, ct = body[:16], body[16:28], body[28:]
    return AESGCM(derive_key(salt=salt, password=password)).decrypt(iv, ct, None)


def to_b64(blob: bytes) -> str:
    return base64.b64encode(blob).decode("ascii")


# The browser-side unlock: fetch the blob, strip MAGIC, derive the key, decrypt. Kept
# here as the canonical JS so every static surface uses the identical scheme. The magic
# bytes are checked as ASCII "LREV1\0". Returns a Uint8Array of the plaintext.
UNLOCK_JS = r"""
async function laplaceUnlock(blobBytes, password){
  const MAGIC = [76,82,69,86,49,0];                 // "LREV1\0"
  for (let i=0;i<MAGIC.length;i++) if (blobBytes[i]!==MAGIC[i]) throw new Error("not a review bundle");
  const body = blobBytes.subarray(MAGIC.length);
  const salt = body.subarray(0,16), iv = body.subarray(16,28), ct = body.subarray(28);
  const km = await crypto.subtle.importKey("raw", new TextEncoder().encode(password),
              "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey(
      {name:"PBKDF2", salt, iterations:__ITER__, hash:"SHA-256"},
      km, {name:"AES-GCM", length:256}, false, ["decrypt"]);
  const pt = await crypto.subtle.decrypt({name:"AES-GCM", iv}, key, ct);
  return new Uint8Array(pt);
}
""".replace("__ITER__", str(PBKDF2_ITER))
