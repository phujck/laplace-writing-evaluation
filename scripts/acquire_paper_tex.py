#!/usr/bin/env python3
"""acquire_paper_tex.py — the TEX ACQUISITION leg of the stage-stores run.

DESIGN_2026-07-15_the-stage-stores.md §1c names the fidelity-ordered route for the 17
PDF-only papers: "(a) arXiv tex sources fetched or supplied (the mechanical operator
then applies everywhere — preferred)". This script IS route (a): it enumerates the
author's published PDFs (``published_corpus/pdfs/*.pdf``), skips the papers that
already have committed tex (``voice_corpus/exemplars/``), and for the rest queries the
arXiv API by title (optionally boosted by a known arXiv id or an author constraint),
requires a CONFIDENT match (title similarity high AND the author list contains
McCaul), and — only for confident matches — fetches the e-print source and extracts
just the ``.tex``/``.bib``/``.bbl`` files (no figures; the repo stays light).

Never guess: a candidate with no confident arXiv match is recorded under
``unmatched`` with a reason, never silently dropped. Route (b)/(c) — PDF text
extraction into a degraded ingest — are NOT this script's job; a paper this script
can't confidently resolve to an arXiv tex source stays PDF-only until a later,
explicitly-named degraded pass picks it up.

Two mechanical sources feed the title guess, both zero-guess (never inferred by the
model):
  1. the PDF filename itself (author/year prefix stripped) — the base method named by
     the task;
  2. when present, ``life_corpus/papers/*.md`` distillates, whose ``provenance``
     frontmatter field names the exact source PDF (a mechanical join key, not fuzzy)
     and sometimes an explicit ``arXiv:NNNN.NNNNN`` id in ``venue`` — used as a
     strictly-better title (and a same-record id hint), never in place of the
     API-side confidence check.

Stdlib only. Network: sequential requests through the proxy (HTTPS_PROXY / CA bundle
honoured via the process environment, same as ``urllib`` always does), ~3s spacing
between requests, at most 2 attempts per request (no unbounded retries). If the arXiv
API is unreachable at all (not just individual lookups failing), the run STOPS and
reports that honestly rather than silently producing an all-unmatched manifest.

Usage:
    python3 scripts/acquire_paper_tex.py [--repo-root DIR] [--dry-run] [--limit N]

Writes:
    published_corpus/tex/<paper_id>/*.{tex,bib,bbl}
    published_corpus/tex/_manifest.json
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_EPRINT = "https://arxiv.org/e-print/{id}"
USER_AGENT = "laplace-tex-acquisition/0.1 (mechanical, polite; contact: gerard.mccaul@gmail.com)"

SLEEP_SECONDS = 3.0
MAX_ATTEMPTS = 2                 # at most 2 attempts total per HTTP request — no unbounded retries
ALLOWED_EXTS = {".tex", ".bib", ".bbl"}
DEDUP_THRESHOLD = 0.72           # title-similarity floor to call a PDF "already have tex"
MATCH_THRESHOLD = 0.60           # title-similarity floor to call an arXiv hit "confident"

STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "via", "and", "to", "for", "with", "from",
    "using", "by", "is", "are", "at", "toward", "towards", "into", "over", "under", "as",
}

_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
_TITLE_RE = re.compile(r"\\title(?:\s*\[[^\]]*\])?\s*\{([^}]*)\}")
_PREFIX_RE = re.compile(r"^(.*?)\s*-\s*(\d{4})\s*-\s*(.*)$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_ARXIV_VENUE_RE = re.compile(r"arXiv:(\d{4}\.\d{4,5})(v\d+)?")


class NoTexSourceError(Exception):
    """The arXiv e-print for a confident match carries no .tex/.bib/.bbl payload."""


# --------------------------------------------------------------------------- #
# text helpers — title cleaning, normalization, similarity
# --------------------------------------------------------------------------- #
def clean_latex_text(s: str) -> str:
    """Strip common LaTeX markup from a title string (\\added{...}, \\\\, braces)."""
    s = s.replace("\\\\", " ")
    s = re.sub(r"\\[a-zA-Z]+\{", "", s)
    s = s.replace("}", "").replace("{", "")
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = s.replace("~", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokens(s: str) -> set[str]:
    return {w for w in normalize(s).split() if len(w) >= 3}


def title_similarity(a: str, b: str) -> float:
    """max(character-sequence ratio, token Dice coefficient) — lenient to the
    truncated-filename case (a is often a near-prefix subset of b's words) while NOT
    using the plain overlap coefficient (|A∩B|/min(|A|,|B|)): that formula lets a
    short, vocabulary-generic guess (e.g. a 4-word thesis title built of common
    physics nouns) score ~0.75 against an unrelated same-author paper purely because
    every one of its few words happens to appear somewhere in a much longer title.
    Dice (2|A∩B|/(|A|+|B|)) charges for the longer title's unmatched tokens too, which
    empirically separates the true genuine-truncation matches from that false-positive
    class at the same confidence threshold."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = tokens(a), tokens(b)
    dice = 2 * len(ta & tb) / (len(ta) + len(tb)) if ta and tb else 0.0
    return max(seq, dice)


def slugify(title: str, maxlen: int = 60) -> str:
    s = normalize(title).replace(" ", "-")
    s = re.sub(r"-+", "-", s).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rsplit("-", 1)[0]
    return s or "paper"


def unique_slug(base: str, taken: set[str]) -> str:
    slug = base
    i = 2
    while slug in taken:
        slug = f"{base}-{i}"
        i += 1
    taken.add(slug)
    return slug


def _looks_like_mccaul(name: str) -> bool:
    return "mccaul" in re.sub(r"[^a-z]", "", name.lower())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# title guess sources
# --------------------------------------------------------------------------- #
def title_from_filename(stem: str) -> tuple[str, bool]:
    """Derive a title guess from a citation-style PDF stem, stripping an
    "<Authors> - <Year> - " prefix when present. Returns (title_guess, mccaul_in_authors)."""
    s = stem.replace("#U2010", "-").replace("_", " ")
    m = _PREFIX_RE.match(s)
    if m:
        authors, _year, title = m.groups()
    else:
        authors, title = "", s
    mccaul_hint = "mccaul" in authors.lower()
    return re.sub(r"\s+", " ", title).strip(), mccaul_hint


def extract_tex_title(text: str) -> str | None:
    """The LAST uncommented \\title{...} in a tex source (draft titles are commented
    out above the live one — see low-rank-approximation/main.tex)."""
    title = None
    for line in text.splitlines():
        if line.strip().startswith("%"):
            continue
        m = _TITLE_RE.search(line)
        if m:
            title = m.group(1)
    return clean_latex_text(title) if title else None


def load_existing_tex_titles(exemplars_dir: Path) -> list[tuple[str, str]]:
    """[(paper_id, title)] for every already-committed voice_corpus/exemplars paper —
    the dedup ground truth so this script never re-fetches what's already there."""
    out: list[tuple[str, str]] = []
    if not exemplars_dir.is_dir():
        return out
    for slug_dir in sorted(p for p in exemplars_dir.iterdir() if p.is_dir()):
        title = None
        for tf in sorted(slug_dir.rglob("*.tex")):
            title = extract_tex_title(tf.read_text(encoding="utf-8", errors="replace"))
            if title:
                break
        if title:
            out.append((slug_dir.name, title))
    return out


def load_life_corpus(root: Path) -> dict[str, dict[str, Any]]:
    """pdf_stem -> {title, venue, arxiv_id, slug, distillate_path} from
    life_corpus/papers/*.md frontmatter. The join key (``provenance``) names the exact
    source PDF filename — mechanical, not fuzzy. Papers without a distillate simply
    aren't in this dict; callers fall back to the filename guess."""
    d = root / "life_corpus" / "papers"
    out: dict[str, dict[str, Any]] = {}
    if not d.is_dir():
        return out
    for md in sorted(d.glob("*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        m = _FRONTMATTER_RE.match(text)
        meta: dict[str, str] = {}
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip()
        hm = re.search(r"(?m)^#\s+(.+)$", text)
        title = hm.group(1).strip() if hm else None
        provenance = meta.get("provenance", "")
        pdf_stem = Path(provenance).stem if provenance else None
        venue = meta.get("venue", "")
        vm = _ARXIV_VENUE_RE.search(venue)
        arxiv_id = (vm.group(1) + (vm.group(2) or "")) if vm else None
        if pdf_stem and title:
            out[pdf_stem] = {
                "title": title, "venue": venue, "arxiv_id": arxiv_id,
                "slug": meta.get("slug"), "distillate_path": str(md.relative_to(root)),
            }
    return out


# --------------------------------------------------------------------------- #
# network — arXiv API + e-print fetch (stdlib urllib; proxy honoured via env)
# --------------------------------------------------------------------------- #
def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503, 504) and attempt < MAX_ATTEMPTS:
                time.sleep(SLEEP_SECONDS)
                continue
            raise RuntimeError(f"HTTP {e.code} for {url}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < MAX_ATTEMPTS:
                time.sleep(SLEEP_SECONDS)
                continue
            raise RuntimeError(f"network error for {url}: {e}") from e
    raise RuntimeError(f"GET {url} failed: {last_err}")


def parse_arxiv_feed(data: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(data)
    entries = []
    for e in root.findall("a:entry", _ATOM_NS):
        id_url = (e.findtext("a:id", default="", namespaces=_ATOM_NS) or "").strip()
        arxiv_id = id_url.rsplit("/", 1)[-1] if id_url else ""
        title = " ".join((e.findtext("a:title", default="", namespaces=_ATOM_NS) or "").split())
        authors = [
            (a.findtext("a:name", default="", namespaces=_ATOM_NS) or "").strip()
            for a in e.findall("a:author", _ATOM_NS)
        ]
        if arxiv_id:
            entries.append({"arxiv_id": arxiv_id, "title": title, "authors": authors})
    return entries


def arxiv_search(query_words: list[str], require_mccaul_author: bool, max_results: int = 8) -> list[dict[str, Any]]:
    """OR-relevance search: any significant title word may hit. An AND-of-all-words
    query is too strict for real titles — Zotero-derived filenames silently drop
    internal hyphens (e.g. "non-conservation" -> "nonconservation"), so a single
    de-hyphenated token can zero out an AND query even though arXiv genuinely has the
    paper. OR lets the surviving words carry a hit; the final confidence gate (title
    similarity + author-list check) still does the precision work, not the query."""
    words = [w for w in query_words if w]
    if not words:
        return []
    clauses = " OR ".join(f'ti:"{w}"' for w in words)
    q = f"({clauses})"
    if require_mccaul_author:
        q = f"{q} AND au:mccaul"
    url = ARXIV_API + "?" + urllib.parse.urlencode({"search_query": q, "start": 0, "max_results": max_results})
    return parse_arxiv_feed(http_get(url))


def arxiv_lookup_by_id(arxiv_id: str) -> list[dict[str, Any]]:
    url = ARXIV_API + "?" + urllib.parse.urlencode({"id_list": arxiv_id, "max_results": 1})
    return parse_arxiv_feed(http_get(url))


def build_query_words(title_guess: str, max_words: int = 8) -> list[str]:
    toks = normalize(title_guess).split()
    # Zotero-style filenames truncate mid-word with no ellipsis, so the trailing raw
    # token is frequently a fragment ("chemic", "expressivity via ... dom") — drop it
    # from the QUERY (not from scoring, which still uses the full guess).
    if len(toks) > 4:
        toks = toks[:-1]
    sig = [t for t in toks if t not in STOPWORDS and len(t) >= 3]
    return (sig or toks)[:max_words]


def search_arxiv_for_title(title_guess: str, require_author: bool) -> tuple[list[dict[str, Any]], str]:
    """OR-relevance query over the significant title words, AND-gated by au:mccaul when
    the filename/distillate indicates McCaul; if that yields nothing, retry once with
    the author constraint relaxed (in case au: field matching is stricter than
    expected). Returns (entries, query_note) for manifest transparency."""
    words = build_query_words(title_guess)
    if not words:
        return [], "ti:()"
    entries = arxiv_search(words, require_author)
    time.sleep(SLEEP_SECONDS)
    note = "ti:(" + " OR ".join(words) + ")" + (" AND au:mccaul" if require_author else "")
    if entries:
        return entries, note
    if require_author:
        entries = arxiv_search(words, False)
        time.sleep(SLEEP_SECONDS)
        note = "ti:(" + " OR ".join(words) + ")  [author constraint relaxed after empty result]"
        if entries:
            return entries, note
    return [], note


def preflight_arxiv() -> tuple[bool, str | None]:
    try:
        url = ARXIV_API + "?" + urllib.parse.urlencode({"search_query": "ti:test", "max_results": 1})
        http_get(url, timeout=20)
        return True, None
    except Exception as e:  # noqa: BLE001 — report any failure honestly, don't hunt workarounds
        return False, str(e)


def fetch_and_extract(arxiv_id: str, dest_dir: Path) -> list[str]:
    """Fetch the e-print at arxiv.org/e-print/<id> and extract only .tex/.bib/.bbl
    members (no figures — the repo stays light). Handles both the multi-file
    (gzipped tar) and single-file (bare gzip) e-print shapes arXiv serves."""
    url = ARXIV_EPRINT.format(id=arxiv_id)
    raw = http_get(url, timeout=60)
    buf = io.BytesIO(raw)
    written: list[str] = []
    try:
        with tarfile.open(fileobj=buf, mode="r:*") as tf:
            used_names: set[str] = set()
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                name = Path(member.name).name
                if not name or name.startswith("."):
                    continue
                ext = Path(name).suffix.lower()
                if ext not in ALLOWED_EXTS:
                    continue
                out_name = name
                i = 2
                while out_name in used_names:
                    out_name = f"{Path(name).stem}_{i}{ext}"
                    i += 1
                used_names.add(out_name)
                fobj = tf.extractfile(member)
                if fobj is None:
                    continue
                data = fobj.read()
                dest_dir.mkdir(parents=True, exist_ok=True)
                (dest_dir / out_name).write_bytes(data)
                written.append(out_name)
        return written
    except tarfile.ReadError:
        pass  # not a tar — fall through to the bare-gzip / single-file case

    try:
        data = gzip.decompress(raw)
    except OSError:
        data = raw
    if data[:4] == b"%PDF":
        raise NoTexSourceError("arxiv e-print is a bare PDF (no LaTeX source available)")
    head = data[:2000].decode("latin-1", errors="replace")
    if "\\documentclass" in head or "\\begin{document}" in head or head.lstrip().startswith("%") or "\\section" in head:
        out_name = f"{re.sub(r'[^A-Za-z0-9._-]', '_', arxiv_id)}.tex"
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / out_name).write_bytes(data)
        written.append(out_name)
        return written
    raise NoTexSourceError(f"unrecognized e-print payload (first bytes: {data[:24]!r})")


# --------------------------------------------------------------------------- #
# per-candidate resolution
# --------------------------------------------------------------------------- #
def resolve_and_fetch(cand: dict[str, Any], tex_out_root: Path, taken_slugs: set[str], dry_run: bool) -> dict[str, Any]:
    pdf: Path = cand["pdf"]
    title_guess: str = cand["title_guess"]
    base_record = {
        "pdf": pdf.name, "title_guess": title_guess, "title_source": cand["title_source"],
    }

    try:
        query_note: str
        entries: list[dict[str, Any]]
        if cand["arxiv_hint"]:
            entries = arxiv_lookup_by_id(cand["arxiv_hint"])
            time.sleep(SLEEP_SECONDS)
            query_note = f"id_list:{cand['arxiv_hint']} (life_corpus venue hint)"
            if not entries:
                entries, query_note = search_arxiv_for_title(title_guess, cand["require_author"])
        else:
            entries, query_note = search_arxiv_for_title(title_guess, cand["require_author"])
    except Exception as e:  # noqa: BLE001 — record, never crash the whole run over one paper
        base_record.update({"reason": f"arxiv query error: {e}", "query": None})
        return {"status": "unmatched", "record": base_record}

    if not entries:
        base_record.update({"reason": "no arxiv results", "query": query_note})
        return {"status": "unmatched", "record": base_record}

    scored = sorted(
        (
            (title_similarity(title_guess, e["title"]), any(_looks_like_mccaul(a) for a in e["authors"]), e)
            for e in entries
        ),
        key=lambda t: t[0], reverse=True,
    )
    # pick the best entry that clears BOTH gates together — the top-scoring entry
    # overall might fail the author check while a slightly lower-scoring one passes
    # both; never settle for "highest score regardless of author."
    confident = [t for t in scored if t[0] >= MATCH_THRESHOLD and t[1]]

    if not confident:
        best_score, best_author_ok, best_entry = scored[0]
        if best_score >= MATCH_THRESHOLD:
            reason = "author list lacks McCaul"
        elif best_author_ok:
            reason = "plausible same-author arxiv hit but title diverges from the guess beyond threshold — flagged for manual review, not auto-matched"
        else:
            reason = "low title similarity"
        base_record.update({
            "reason": f"{reason} (best_score={best_score:.3f}, best_title={best_entry['title']!r})",
            "best_arxiv_id": best_entry["arxiv_id"], "best_score": round(best_score, 3), "query": query_note,
        })
        return {"status": "unmatched", "record": base_record}

    best_score, best_author_ok, best_entry = confident[0]

    arxiv_id = best_entry["arxiv_id"]
    slug_base = slugify(best_entry["title"]) or slugify(title_guess)
    paper_id = unique_slug(slug_base, taken_slugs)

    if dry_run:
        record = {
            "paper_id": paper_id, "arxiv_id": arxiv_id, "title": best_entry["title"],
            "title_guess": title_guess, "title_source": cand["title_source"],
            "match_score": round(best_score, 3), "query": query_note,
            "files": [], "fetched_at": None, "note": "dry-run: not fetched",
        }
        return {"status": "matched", "record": record}

    dest = tex_out_root / paper_id
    try:
        files = fetch_and_extract(arxiv_id, dest)
        time.sleep(SLEEP_SECONDS)
    except NoTexSourceError as e:
        base_record.update({
            "reason": f"confident arxiv match {arxiv_id} but {e}",
            "arxiv_id": arxiv_id, "best_title": best_entry["title"],
            "best_score": round(best_score, 3), "query": query_note,
        })
        return {"status": "unmatched", "record": base_record}
    except Exception as e:  # noqa: BLE001
        base_record.update({
            "reason": f"fetch error for {arxiv_id}: {e}",
            "arxiv_id": arxiv_id, "best_title": best_entry["title"],
            "best_score": round(best_score, 3), "query": query_note,
        })
        return {"status": "unmatched", "record": base_record}

    if not files:
        base_record.update({
            "reason": f"confident arxiv match {arxiv_id} but no .tex/.bib/.bbl in e-print",
            "arxiv_id": arxiv_id, "best_title": best_entry["title"],
            "best_score": round(best_score, 3), "query": query_note,
        })
        return {"status": "unmatched", "record": base_record}

    record = {
        "paper_id": paper_id, "arxiv_id": arxiv_id, "title": best_entry["title"],
        "title_guess": title_guess, "title_source": cand["title_source"],
        "match_score": round(best_score, 3), "query": query_note,
        "files": sorted(f"published_corpus/tex/{paper_id}/{f}" for f in files),
        "fetched_at": now_iso(),
    }
    return {"status": "matched", "record": record}


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def build_candidates(root: Path, existing_titles: list[tuple[str, str]],
                      life_corpus: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pdfs_dir = root / "published_corpus" / "pdfs"
    pdf_files = sorted(pdfs_dir.glob("*.pdf")) if pdfs_dir.is_dir() else []

    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for pdf in pdf_files:
        stem = pdf.stem
        lc = life_corpus.get(stem)
        _, mccaul_in_name = title_from_filename(stem)
        if lc:
            title_guess = lc["title"]
            title_source = "life_corpus"
            arxiv_hint = lc.get("arxiv_id")
        else:
            title_guess, _ = title_from_filename(stem)
            title_source = "filename"
            arxiv_hint = None
        require_author = mccaul_in_name or bool(lc)

        best_dup: tuple[str, float] | None = None
        for pid, t in existing_titles:
            s = title_similarity(title_guess, t)
            if best_dup is None or s > best_dup[1]:
                best_dup = (pid, s)

        if best_dup and best_dup[1] >= DEDUP_THRESHOLD:
            skipped.append({
                "pdf": pdf.name, "title_guess": title_guess,
                "matched_paper_id": best_dup[0], "score": round(best_dup[1], 3),
            })
            continue

        candidates.append({
            "pdf": pdf, "stem": stem, "title_guess": title_guess,
            "title_source": title_source, "arxiv_hint": arxiv_hint,
            "require_author": require_author,
        })

    return candidates, skipped


def print_report(manifest: dict[str, Any]) -> None:
    c = manifest["counts"]
    print("# acquire_paper_tex — TEX ACQUISITION leg (route 1c-a: arXiv sources)")
    print(f"pdf_total={c['pdf_total']}  skipped_duplicate={c['skipped_duplicate']}  "
          f"candidates={c['candidates']}  matched={c['matched']}  unmatched={c['unmatched']}")
    print()
    print("MATCHED:")
    for r in manifest["matched"]:
        print(f"  {r['paper_id']:<50} arxiv={r['arxiv_id']:<16} score={r['match_score']:<6} files={len(r['files'])}")
    print()
    print("UNMATCHED (never guessed — reason named):")
    for r in manifest["unmatched"]:
        print(f"  {r['pdf']:<60} reason={r['reason']}")
    print()
    print("SKIPPED (already have tex):")
    for r in manifest["skipped_duplicate"]:
        print(f"  {r['pdf']:<60} -> {r['matched_paper_id']} (score={r['score']})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-root", default=str(_REPO_ROOT))
    ap.add_argument("--dry-run", action="store_true",
                     help="resolve arXiv matches but skip the e-print fetch/extract step")
    ap.add_argument("--limit", type=int, default=None, help="cap the number of candidates processed (debug)")
    ap.add_argument("--quiet", action="store_true", help="write the manifest, print nothing")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    root = Path(args.repo_root).resolve()
    tex_out_root = root / "published_corpus" / "tex"
    exemplars_dir = root / "voice_corpus" / "exemplars"

    existing_titles = load_existing_tex_titles(exemplars_dir)
    life_corpus = load_life_corpus(root)
    candidates, skipped = build_candidates(root, existing_titles, life_corpus)
    if args.limit:
        candidates = candidates[: args.limit]

    manifest: dict[str, Any] = {
        "schema": "published-tex-acquisition/0.1",
        "generated_at": now_iso(),
        "route": "DESIGN_2026-07-15_the-stage-stores.md §1c(a) — arXiv tex sources, preferred route",
        "existing_tex_papers": [{"paper_id": pid, "title": t} for pid, t in existing_titles],
        "skipped_duplicate": skipped,
        "matched": [],
        "unmatched": [],
    }

    pdfs_dir = root / "published_corpus" / "pdfs"
    pdf_total = sum(1 for _ in pdfs_dir.glob("*.pdf")) if pdfs_dir.is_dir() else 0

    if candidates:
        ok, err = preflight_arxiv()
        if not ok:
            for cand in candidates:
                manifest["unmatched"].append({
                    "pdf": cand["pdf"].name, "title_guess": cand["title_guess"],
                    "title_source": cand["title_source"],
                    "reason": f"STOPPED: arXiv API unreachable via proxy ({err}) — "
                              f"no mirrors or workarounds attempted, per instruction",
                })
            manifest["stopped"] = True
            manifest["stop_reason"] = err
        else:
            taken_slugs = {pid for pid, _ in existing_titles}
            if tex_out_root.is_dir():
                taken_slugs |= {p.name for p in tex_out_root.iterdir() if p.is_dir()}
            for cand in candidates:
                result = resolve_and_fetch(cand, tex_out_root, taken_slugs, dry_run=args.dry_run)
                manifest["matched" if result["status"] == "matched" else "unmatched"].append(result["record"])

    manifest["counts"] = {
        "pdf_total": pdf_total,
        "skipped_duplicate": len(skipped),
        "candidates": len(candidates),
        "matched": len(manifest["matched"]),
        "unmatched": len(manifest["unmatched"]),
    }

    tex_out_root.mkdir(parents=True, exist_ok=True)
    manifest_path = tex_out_root / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not args.quiet:
        print_report(manifest)
        print()
        print(f"wrote: {manifest_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
