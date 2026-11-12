"""The website exporter (scripts/export_site.py): the sealed bundle is the public
artifact, so pin the seal - bake, encrypt, decrypt-as-the-browser-would, and the
wrong-passphrase rejection. Encrypt-by-default is the posture (unpublished disclosure);
--plain stays the author's per-corpus call and is not exercised here."""
import base64
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))


def test_sealed_bundle_roundtrip(tmp_path):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    import export_site

    data = export_site.bake_data("subset-sum-itqde")
    assert data["n_nodes"] > 300 and data["spine"], "the bake must carry the corpus"
    inner = export_site.inner_html(data)
    # A node id drawn from the live bake itself (the spine's first node) rather than
    # a hardcoded label: THE RUN reshapes the corpus, so the seal is pinned against
    # whatever the bake actually spined this run — it must round-trip into inner and
    # be absent from the sealed page.
    probe = data["spine"][0]["id"]
    assert probe in inner

    sealed = export_site.encrypt_bundle(inner, "pin-the-seal")
    assert probe not in sealed, "plaintext must not leak into the sealed page"

    blob = base64.b64decode(re.search(r'atob\("([^"]+)"\)', sealed).group(1))
    salt, iv, ct = blob[:16], blob[16:28], blob[28:]
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=export_site.PBKDF2_ITER).derive(b"pin-the-seal")
    plain = AESGCM(key).decrypt(iv, ct, None).decode("utf-8")
    assert plain == inner, "the browser-path decrypt must return the exact inner page"

    bad = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=export_site.PBKDF2_ITER).derive(b"wrong")
    try:
        AESGCM(bad).decrypt(iv, ct, None)
        raise AssertionError("wrong passphrase must not decrypt")
    except Exception:
        pass
