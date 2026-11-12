"""FROZEN (2026-07-08, the shelving): the remote review surface is shelved - the
deployed site stays as-is, no further development here. The local projection
viewer carries review now (pdf.js render layer + the mechanisms this surface
pioneered). The anchor-band baking in this module stays IMPORTABLE - it is the
source for pre-baked synctex bands if the local viewer ever wants them.

Build the encrypted static REVIEW bundle (``data.enc``) for the website review
surface (``phujck.github.io/review/ssc/``) from a compiled whitepaper.

The website app (``review/ssc/index.html``) is a self-contained, passphrase-gated
PDF-commentary surface. It fetches ``data.enc`` - a binary
``MAGIC(LREV1\\0) + salt(16) + iv(12) + AES-256-GCM(JSON)`` sealed under PBKDF2-SHA256
(200k iters), decrypting entirely in-browser via WebCrypto. The plaintext is the DATA
object the app renders: rendered pages, per-page provenance anchor bands, the selectable
text layer, the provenance spans, the seeded feedback, and (optionally) a baked GitHub
token so reviewers' comments push automatically.

This is the committed reconstruction of the previously ad-hoc packer. It is a frozen
snapshot of exactly what the live REVIEW MODE (``projection_viewer.py``) computes on
demand, so every field is built through the SAME mechanisms the viewer already trusts:
``render_pages`` (pages/dpi), ``text_layer`` (word boxes), ``synctex_anchor`` grid-sampled
into y-bands (anchors), ``load_map``/``parse_map`` (spans), ``doc_model`` (root).

Keying: the passphrase is reused (the link + password already shared with reviewers stay
valid), supplied via ``--password`` or ``$LAPLACE_SITE_PASSWORD``. The baked github_token
is LIFTED from the existing bundle by decrypting it with the same passphrase - never
re-handed.

Usage:
  # validate structure only (no passphrase needed) - writes plaintext data.json:
  python scripts/build_review_bundle.py --dump-plain /tmp/data.json
  # seal for deploy (reuses passphrase, lifts token from the current bundle):
  LAPLACE_SITE_PASSWORD=... python scripts/build_review_bundle.py \
      --old ../phujck.github.io/review/ssc/data.enc \
      --out ../phujck.github.io/review/ssc/data.enc
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.manuscript import projection_viewer as pv  # noqa: E402

TEX = "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex"
CORPUS = "subset-sum-itqde"
INBOX = ("synthetics papers/subset-sum-itqde/manuscript/whitepaper/feedback/inbox")

MAGIC = b"LREV1\x00"          # matches index.html MAGIC=[76,82,69,86,49,0]
ITER = 200_000               # matches index.html ITER
ANCHOR_STEP_PT = 8.0         # y-sampling step for synctex bands (PDF points)


# --------------------------------------------------------------------------- pages
WEBP_QUALITY = 80            # keeps pixel dims (anchor geometry via naturalHeight*72/dpi unchanged)


def _pages_b64(rp: dict) -> list[str]:
    """Rendered pages as data-URIs. Re-encode the PNGs to WebP - what the deployed
    bundle uses, and ~3x lighter than a bare PNG bundle (a real regression on the mobile
    surface otherwise). Pixel dimensions are preserved, so DATA.dpi and every anchor/pin
    coordinate (all derived from img.naturalHeight*72/dpi) are unchanged."""
    import io
    from PIL import Image
    rr = pv._repo_root().resolve()
    out = []
    for rel in rp["pages"]:
        png = (rr / rel).read_bytes()
        try:
            im = Image.open(io.BytesIO(png)).convert("RGB")
            buf = io.BytesIO()
            im.save(buf, format="WEBP", quality=WEBP_QUALITY, method=6)
            out.append("data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode("ascii"))
        except Exception:                                    # noqa: BLE001 - PNG fallback
            out.append("data:image/png;base64," + base64.b64encode(png).decode("ascii"))
    return out


# ------------------------------------------------------------------------- anchors
def _page_anchors(page: int, page_w: float, page_h: float) -> list[dict]:
    """Grid-sample synctex down the page and coalesce contiguous same-source runs
    into ``{y0,y1,section,file,line,nodes}`` bands (PDF points, the app's space)."""
    xs = [page_w * 0.30, page_w * 0.5, page_w * 0.15]   # try left col, centre, margin
    bands: list[dict] = []
    y = 2.0
    while y < page_h:
        hit = None
        for x in xs:
            a = pv.synctex_anchor(TEX, page, x, y)
            if "error" not in a and a.get("line"):
                hit = a
                break
        if hit is not None:
            key = (hit.get("file", ""), hit.get("line", 0), hit.get("section", ""),
                   tuple(hit.get("nodes", []) or []))
            if bands and bands[-1]["_key"] == key:
                bands[-1]["y1"] = round(y, 1)
            else:
                bands.append({"_key": key, "y0": round(y, 1), "y1": round(y, 1),
                              "section": hit.get("section", ""), "file": hit.get("file", ""),
                              "line": hit.get("line", 0), "nodes": hit.get("nodes", []) or []})
        y += ANCHOR_STEP_PT
    for b in bands:
        b.pop("_key", None)
    return bands


def _build_anchors(n_pages: int, textlayer: list[dict]) -> list[list[dict]]:
    anchors = []
    for i in range(n_pages):
        pg = textlayer[i] if i < len(textlayer) else {}
        w = float(pg.get("w") or 612.0)
        h = float(pg.get("h") or 792.0)
        anchors.append(_page_anchors(i + 1, w, h))
        print(f"  anchors page {i+1}/{n_pages}: {len(anchors[-1])} bands", file=sys.stderr)
    return anchors


# --------------------------------------------------------------------- spans/titles
_SEC_RE = re.compile(r"\\(?:sub)*section\*?\{([^}]*)\}")


def _spans_and_titles(files: list[dict]) -> tuple[list[dict], dict]:
    spans: list[dict] = []
    sec_titles: dict[str, str] = {}
    for f in files:
        p = pv._safe_path(f["file"])
        if not (p and p.is_file()):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        for s in pv.load_map(p):
            sec = s.get("section", "")
            spans.append({"file": f["file"], "start_line": s.get("start_line", 0),
                          "end_line": s.get("end_line", 0), "section": sec,
                          "nodes": s.get("nodes", []) or []})
            if sec and sec not in sec_titles:
                # nearest \section title at/after the span start (cosmetic rail header)
                for ln in lines[max(0, s.get("start_line", 1) - 1):]:
                    m = _SEC_RE.search(ln)
                    if m:
                        sec_titles[sec] = m.group(1).strip()
                        break
    return spans, sec_titles


# ------------------------------------------------------------------------ feedback
def _feedback() -> list[dict]:
    d = ROOT / INBOX
    recs = []
    if d.is_dir():
        for jf in sorted(d.glob("*.json")):
            try:
                recs.append(json.loads(jf.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass
    return recs


# ---------------------------------------------------------------------------- DATA
def build_data() -> dict:
    rp = pv.render_pages(TEX)
    if "error" in rp:
        raise SystemExit(f"render_pages: {rp['error']}")
    print(f"pages: {rp['n_pages']} @ {rp['dpi']}dpi (synctex_fresh={rp.get('synctex_fresh')})",
          file=sys.stderr)
    if not rp.get("synctex_fresh", True):
        raise SystemExit("synctex stale (pdf newer than synctex) - recompile before packing")
    tl = pv.text_layer(TEX).get("pages", [])
    dm = pv.doc_model(TEX)
    spans, sec_titles = _spans_and_titles(dm["files"])
    print("building anchors (grid-sampled synctex)...", file=sys.stderr)
    anchors = _build_anchors(rp["n_pages"], tl)
    net = pv._network(CORPUS) or {"nodes": {}}
    nodes = {nid: {"kind": nd.get("kind")} for nid, nd in net.get("nodes", {}).items()}
    data = {
        "corpus": CORPUS, "root": dm["root"], "dpi": rp["dpi"], "n_pages": rp["n_pages"],
        "pages": _pages_b64(rp), "textlayer": tl, "anchors": anchors, "spans": spans,
        "sec_titles": sec_titles, "feedback": _feedback(), "nodes": nodes,
    }
    print(f"DATA: {data['n_pages']} pages, {sum(len(a) for a in anchors)} anchor bands, "
          f"{len(spans)} spans, {len(sec_titles)} sec_titles, {len(data['feedback'])} feedback, "
          f"{len(nodes)} nodes", file=sys.stderr)
    return data


# ------------------------------------------------------------------------- crypto
def _derive(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                      iterations=ITER).derive(password.encode("utf-8"))


def decrypt(blob: bytes, password: str) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if blob[:len(MAGIC)] != MAGIC:
        raise SystemExit("old bundle missing MAGIC header")
    body = blob[len(MAGIC):]
    salt, iv, ct = body[:16], body[16:28], body[28:]
    pt = AESGCM(_derive(password, salt)).decrypt(iv, ct, None)
    return json.loads(pt.decode("utf-8"))


def encrypt(data: dict, password: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    pt = json.dumps(data, ensure_ascii=False).encode("utf-8")
    ct = AESGCM(_derive(password, salt)).encrypt(iv, pt, None)
    return MAGIC + salt + iv + ct


# ---------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", help="existing data.enc to lift the baked github_token from")
    ap.add_argument("--out", help="write the sealed data.enc here")
    ap.add_argument("--dump-plain", help="write plaintext DATA json here (validation, no seal)")
    ap.add_argument("--password", default=None)
    ap.add_argument("--git-head", default=None, help="record this laplace commit in DATA (info)")
    a = ap.parse_args()

    data = build_data()
    if a.git_head:
        data["git_head"] = a.git_head

    if a.dump_plain and not a.out:
        Path(a.dump_plain).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        sz = Path(a.dump_plain).stat().st_size
        print(f"plaintext DATA -> {a.dump_plain} ({sz//1024} KB)")
        return 0

    pw = a.password or os.environ.get("LAPLACE_SITE_PASSWORD")
    if not pw:
        raise SystemExit("need a passphrase: --password or $LAPLACE_SITE_PASSWORD "
                         "(reuse the existing one so the reviewer link stays valid)")

    if a.old:
        old = decrypt(Path(a.old).read_bytes(), pw)
        tok = old.get("github_token")
        if tok:
            data["github_token"] = tok
            print(f"baked github_token lifted from {a.old} ({len(tok)} chars, value hidden)",
                  file=sys.stderr)
        else:
            print(f"WARNING: no github_token in {a.old} - shipping tokenless", file=sys.stderr)

    blob = encrypt(data, pw)
    # roundtrip self-check
    back = decrypt(blob, pw)
    assert back["n_pages"] == data["n_pages"], "roundtrip n_pages mismatch"
    assert ("github_token" in back) == ("github_token" in data), "roundtrip token mismatch"
    if a.dump_plain:
        Path(a.dump_plain).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = a.out or "data.enc"
    Path(out).write_bytes(blob)
    print(f"sealed bundle -> {out} ({len(blob)//1024} KB); roundtrip OK; "
          f"token={'baked' if 'github_token' in data else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
