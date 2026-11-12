"""ingest_gemini.py - normalise a "Notes by Gemini" meeting doc into a call skeleton.

THE GEMINI PIPE (built 2026-09-21, his drop). The sibling of ``ingest_otter.py``. Where Otter
needs a manual export from a web app because it ships no Linux client, Gemini writes straight
into Drive: a Meet with Gemini note-taking on drops a ``<Title> - <date> - Notes by Gemini``
Google Doc into ``Meet Recordings/`` or into the recurring-meeting folder under
``Google Meet/``. Since 2026-09-21 that Drive is mounted at ``~/GoogleDrive`` (rclone, systemd
user unit ``rclone-gdrive.service``), so the drop is reachable as an ordinary path.

NOTE ON THE MOUNT TRAP: a "Notes by Gemini" file is a NATIVE GOOGLE DOC, not a stored
.docx. Google Docs have no fixed byte size - Drive exports them on demand - so the rclone FUSE
mount lists them but cannot serve a read, and every open through ``~/GoogleDrive`` fails with
``EIO``. They must be fetched with ``rclone copy``. That is why ``--remote`` exists and is the
supported route; ``--scan`` is only for .docx files already on local disk.

NOTE ON THE TWO FOLDERS: Gemini files a recurring meeting under
``Google Meet/<Meeting> (recurring)/`` and a one-off under ``Meet Recordings/``. Reading only
one of them silently loses the newest transcript. ``--scan`` walks both.

A Gemini doc is TWO documents stapled together, and they are not the same kind of thing:

1. Gemini's own notes - Summary / Decisions / Next steps / Details, plus the "Quick notes"
   bullets. These are MODEL OUTPUT about the meeting. They are useful and they are wrong
   sometimes; they are banked as ``notes_gemini.md`` and never treated as what was said.
2. the verbatim timestamped transcript under the ``... - Transcript`` heading. This is the
   nearest thing to the room and is banked as ``transcript_gemini.md``.

The byte-exact ``.docx`` export is banked beside them as ``source_gemini.docx`` so the
conversion is always re-checkable against its input. Every banked file's size and SHA-256 goes
into the stub header, per the house pattern.

Like the Otter pipe this is DELIBERATELY not an extractor. It never calls a model, never
guesses an attribution and never writes a claim. It writes
``evidence/intake_queue/call_<date>_<slug>/`` and stops. A session reconstructs the extraction
against the house pattern and moves the directory to ``evidence/call_<date>_<slug>/``; until
that happens the meeting is NOT in the collection.

Requires ``pandoc`` for the docx->markdown conversion (present on this machine at
/usr/bin/pandoc). It is the one external tool in the path and the script says so loudly if it
is missing rather than half-ingesting.

Idempotent in the way that matters: a meeting already carried in is skipped BEFORE the export
is paid for. Three guards, strongest first; ``--reingest`` overrides all of them:

1. The collection itself. Every ``evidence/call_*/extraction.md`` (authored) and every
   ``evidence/intake_queue/call_*/extraction.md`` (stub) names the Drive doc it came from in a
   backticked path on its provenance line, and the pipe matches on the doc's FILENAME read out
   of that line. The filename is the doc's one stable identity: sessions rename call
   directories (the pipe's ``call_2026-08-12_jackandrew`` is in the collection as
   ``call_2026-08-12_jack-hampson-andrew-graham``) and Drive moves folders
   (``Meet Recordings/`` went under ``Google Meet/`` between September and October 2026), so
   neither the directory name nor the full path is one. On 2026-10-08 the directory-name check
   alone re-exported every old meeting into the queue; this guard is the repair. A meeting
   authored from another raw (a pasted transcript) carries the same kind of line, written by
   hand, naming its Gemini doc.
2. The directory the doc would land in, ``call_<date>_<slug>`` from the filename alone, already
   existing in ``evidence/`` or in the queue: the fallback for a directory whose extraction
   does not name the doc yet.
3. The seen-ledger ``.ingested_gemini.json``, keyed on the full Drive path.

``--dry-run`` prints every doc's disposition and exports nothing; run it when the listing has
changed to see what a real run would pay for. Re-running refreshes the raws of a doc it does
export and leaves an existing authored ``extraction.md`` alone (an authored extraction is never
overwritten by the machine).

Usage:
    scripts/laplace-python scripts/ingest_gemini.py <doc.docx> [<doc.docx> ...]
    scripts/laplace-python scripts/ingest_gemini.py --remote gdrive: --dry-run
    scripts/laplace-python scripts/ingest_gemini.py --remote gdrive: --limit 3
    scripts/laplace-python scripts/ingest_gemini.py --scan ~/some/local/dir

Exit codes: 0 all ingested (or nothing matched under --scan, or --dry-run), 1 one or more failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QUEUE = REPO / "evidence" / "intake_queue"
LEDGER = QUEUE / ".ingested_gemini.json"

# Gemini files recurring meetings and one-offs in different places; walk both.
SCAN_SUBDIRS = ("Meet Recordings", "Google Meet")
GEMINI_GLOB = "*Notes by Gemini*.docx"

# Google rewrites "/" in a doc title as the fullwidth solidus U+FF0F.
DATE_RE = re.compile(r"(\d{4})[/／](\d{1,2})[/／](\d{1,2})\s+(\d{1,2}):(\d{2})")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
TRANSCRIPT_HEAD_RE = re.compile(r"^#{1,3}\s+.*-\s*Transcript\s*$", re.MULTILINE)
STAMP_RE = re.compile(r"^#{1,3}\s+(\d{2}:\d{2}:\d{2})\s*$", re.MULTILINE)


def rclone_find(remote: str) -> list[tuple[str, str]]:
    """(modtime, full remote path) for every Gemini doc, newest first."""
    rows: list[tuple[str, str]] = []
    for sub in SCAN_SUBDIRS:
        out = subprocess.run(
            ["rclone", "lsf", f"{remote}{sub}", "--recursive", "--include", GEMINI_GLOB,
             "--format", "tp", "--separator", "\t"],
            capture_output=True, text=True, timeout=600,
        )
        if out.returncode != 0:
            continue
        for line in out.stdout.splitlines():
            if "\t" not in line:
                continue
            when, rel = line.split("\t", 1)
            if rel.endswith("/"):
                continue
            rows.append((when, f"{remote}{sub}/{rel}"))
    rows.sort(reverse=True)
    return rows


def target_name(filename: str) -> str | None:
    """The call directory a doc WOULD land in, read from its filename alone.

    Cheap on purpose: it lets --remote skip a meeting that is already in the collection
    without paying for the Drive export first.
    """
    m = DATE_RE.search(filename)
    if not m:
        return None
    y, mo, d, _hh, _mm = (int(x) for x in m.groups())
    return f"call_{y:04d}-{mo:02d}-{d:02d}_{slugify(filename.split(' - ')[0].strip())}"


# A backticked path naming a Gemini doc, as the stub writes it ("Source: Google Doc exported
# via rclone from `gdrive:...`") and as a session writes it by hand beside a pasted raw. Only
# the filename inside it is read; see collection_index for why.
DOC_REF_RE = re.compile(r"`([^`\n]*Notes by Gemini[^`\n]*\.docx)`")


def doc_key(remote_path: str) -> str:
    """The doc's filename: ``<Title> - <YYYY／MM／DD HH:MM> BST - Notes by Gemini.docx``.

    Google mints it from the meeting title and start minute. It is the one identity that
    survives both a session renaming the call directory and Drive moving the folder above it.
    """
    return remote_path.rsplit("/", 1)[-1]


def collection_index(repo: Path, queue: Path) -> dict[str, tuple[str, Path]]:
    """doc filename -> ("collection" | "queued", directory) for every doc an extraction.md names.

    The extraction line is the truth, not the directory name: ``evidence/call_*/extraction.md``
    names the doc an authored extraction came from, and the stub in the queue names the doc
    waiting to be authored. The collection is read first so a doc that is both authored and
    still sitting in the queue reports as in the collection.
    """
    index: dict[str, tuple[str, Path]] = {}
    for state, root in (("collection", repo / "evidence"), ("queued", queue)):
        for ext in sorted(root.glob("call_*/extraction.md")):
            text = ext.read_text(encoding="utf-8", errors="replace")
            for ref in DOC_REF_RE.findall(text):
                index.setdefault(doc_key(ref), (state, ext.parent))
    return index


def _rel(path: Path, repo: Path) -> str:
    try:
        return str(path.relative_to(repo))
    except ValueError:
        return str(path)


def disposition(rpath: str, index: dict, ledger: dict, repo: Path, queue: Path) -> tuple[str, str] | None:
    """Why this doc is NOT exported: (state, detail), or None when it is genuinely new.

    Strongest guard first: an extraction names the doc; the date+slug directory exists; the
    seen-ledger has the Drive path. The caller bypasses all three under ``--reingest``.
    """
    key = doc_key(rpath)
    hit = index.get(key)
    if hit:
        state, d = hit
        if state == "collection":
            return state, f"in the collection as {_rel(d, repo)}"
        return state, f"queued as {_rel(d, repo)}, awaiting authoring"
    name = target_name(key)
    if name:
        if (repo / "evidence" / name).is_dir():
            return "collection", f"in the collection as evidence/{name} (date+slug; its extraction.md does not name the doc)"
        if (queue / name).is_dir():
            return "queued", f"queued as {_rel(queue / name, repo)} (date+slug; its extraction.md does not name the doc)"
    if rpath in ledger:
        return "ledger", "in the seen-ledger (--reingest to force)"
    return None


def rclone_fetch(remote_path: str, dest_dir: Path) -> Path:
    """Google Docs cannot be read through the mount; export them with rclone copyto."""
    dest = dest_dir / Path(remote_path).name
    out = subprocess.run(
        ["rclone", "copyto", remote_path, str(dest)],
        capture_output=True, text=True, timeout=900,
    )
    if out.returncode != 0 or not dest.exists():
        raise RuntimeError(f"rclone could not export {remote_path}: {out.stderr.strip()[:200]}")
    return dest


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_-]+", "-", text).strip("-") or "meeting"


def to_markdown(docx: Path) -> str:
    if not shutil.which("pandoc"):
        raise RuntimeError("pandoc is not installed; cannot convert the Gemini docx")
    out = subprocess.run(
        ["pandoc", "-f", "docx", "-t", "markdown", "--wrap=none", str(docx)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"pandoc failed: {out.stderr.strip()[:300]}")
    return out.stdout


def parse(docx: Path, md: str) -> dict:
    """Read only what a parser can actually see. Never infer a name."""
    m = DATE_RE.search(docx.name)
    if not m:
        raise RuntimeError(f"no meeting date in filename: {docx.name}")
    y, mo, d, hh, mm = (int(x) for x in m.groups())
    date = f"{y:04d}-{mo:02d}-{d:02d}"
    title = docx.name.split(" - ")[0].strip()

    split = TRANSCRIPT_HEAD_RE.search(md)
    notes = md[: split.start()].rstrip() if split else md.rstrip()
    transcript = md[split.start():].rstrip() if split else ""

    stamps = STAMP_RE.findall(transcript)
    # Emails appear in Gemini's attendee line near the top of the notes.
    emails, seen = [], set()
    for e in EMAIL_RE.findall(notes[:4000]):
        if e.lower() not in seen and "qualtrics" not in e:
            seen.add(e.lower()); emails.append(e)
    return {
        "date": date, "time": f"{hh:02d}:{mm:02d}", "title": title,
        "slug": slugify(title), "notes": notes, "transcript": transcript,
        "attendees": emails, "last_stamp": stamps[-1] if stamps else None,
        "n_stamps": len(stamps), "had_transcript": bool(split),
    }


def stub(meta: dict, banked: list[tuple[str, int, str]], source: str) -> str:
    att = "\n".join(f"  - `{e}`" for e in meta["attendees"]) or "  - (none emitted by Gemini)"
    files = "\n".join(f"  - `{n}`: {s:,} bytes; SHA-256 `{h}`." for n, s, h in banked)
    warn = "" if meta["had_transcript"] else (
        "\n> **NO VERBATIM TRANSCRIPT IN THIS DOC.** Gemini emitted notes only; there is no\n"
        "> record of what was actually said. Treat every line below as model output.\n")
    return f"""# Extraction — {meta['title']}, {meta['date']} — STUB, NOT YET AUTHORED

> Machine-written landing pad from `scripts/ingest_gemini.py`. It states only what a parser
> could read. It contains **no findings and no attributions**. A session reconstructs the
> extraction against the house pattern (see
> `evidence/call_2026-08-19_techspert-requirements/extraction.md`), then moves this directory
> to `evidence/call_{meta['date']}_{meta['slug']}/`. Until then this meeting is **not in the
> collection**.
{warn}
## Provenance and perimeter

- Source: Google Doc exported via rclone from `{source}`.
- Meeting date {meta['date']}, start {meta['time']} BST, as written in the doc title.
- Banked byte-for-byte:
{files}
- Transcript segments: {meta['n_stamps']}; last timestamp {meta['last_stamp'] or 'n/a'}.
- Attendee addresses as Gemini listed them (addresses, NOT verified attribution of speech):
{att}
- INTERNAL / commercially sensitive. Company meeting material. Nothing here licenses
  outward use.

## What a parser could NOT read

- **Who said what.** The transcript carries Gemini's speaker labels; they are unverified.
- **Whether Gemini's Summary / Decisions / Next steps are true.** They are model output about
  the meeting, banked in `notes_gemini.md`, and are not evidence of what was said.
- Anything requiring judgement: the decisions actually taken, what was agreed vs floated,
  commitments, numbers and their status. That is the authoring step.

## What the room converged on

*(unauthored — this section is the session's job)*
"""


def ingest(docx: Path, queue: Path, reingest: bool, source_label: str | None = None) -> Path:
    md = to_markdown(docx)
    meta = parse(docx, md)
    target = queue / f"call_{meta['date']}_{meta['slug']}"
    target.mkdir(parents=True, exist_ok=True)

    banked: list[tuple[str, int, str]] = []
    shutil.copy2(docx, target / "source_gemini.docx")
    writes = {"notes_gemini.md": meta["notes"]}
    if meta["transcript"]:
        writes["transcript_gemini.md"] = meta["transcript"]
    for name, body in writes.items():
        (target / name).write_text(body + "\n", encoding="utf-8")
    for name in ["source_gemini.docx", *writes]:
        p = target / name
        banked.append((name, p.stat().st_size, sha256(p)))

    ext = target / "extraction.md"
    if ext.exists() and not reingest and "STUB, NOT YET AUTHORED" not in ext.read_text(encoding="utf-8")[:200]:
        print(f"  kept authored extraction.md in {target.name}")
    else:
        ext.write_text(stub(meta, banked, source_label or str(docx)), encoding="utf-8")
    return target


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs", nargs="*", type=Path)
    ap.add_argument("--remote", help="rclone remote to export from, e.g. 'gdrive:' (SUPPORTED ROUTE)")
    ap.add_argument("--scan", type=Path, help="walk local disk for already-exported .docx files")
    ap.add_argument("--limit", type=int, help="with --scan, take only the N most recent")
    ap.add_argument("--queue", type=Path, default=QUEUE)
    ap.add_argument("--reingest", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="print every doc's disposition; export nothing, write nothing")
    args = ap.parse_args(argv)

    args.queue.mkdir(parents=True, exist_ok=True)
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    docs: list[Path] = list(args.docs)
    labels: dict[Path, str] = {}
    tmp: Path | None = None
    if args.remote:
        rows = rclone_find(args.remote)
        if args.limit:
            rows = rows[: args.limit]
        index = collection_index(REPO, args.queue)
        counts = {"collection": 0, "queued": 0, "ledger": 0, "new": 0}
        if rows and not args.dry_run:
            tmp = Path(tempfile.mkdtemp(prefix="gemini-export-"))
        for when, rpath in rows:
            why = None if args.reingest else disposition(rpath, index, ledger, REPO, args.queue)
            if why:
                state, detail = why
                counts[state] += 1
                print(f"skip  {doc_key(rpath)}: {detail}")
                continue
            counts["new"] += 1
            if args.dry_run:
                print(f"NEW   {doc_key(rpath)}: would export to {args.queue.name}/{target_name(doc_key(rpath))}")
                continue
            try:
                local = rclone_fetch(rpath, tmp)
                docs.append(local); labels[local] = rpath
            except Exception as exc:  # noqa: BLE001
                print(f"FAILED export {rpath}: {exc}", file=sys.stderr)
        print(f"{len(rows)} Gemini docs on {args.remote}: {counts['collection']} in the collection, "
              f"{counts['queued']} queued, {counts['ledger']} seen-ledger only, {counts['new']} new")
    if args.scan:
        found = []
        for sub in SCAN_SUBDIRS:
            root = args.scan / sub
            if root.is_dir():
                found += [p for p in root.rglob(GEMINI_GLOB) if p.is_file()]
        found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        docs += found[: args.limit] if args.limit else found
    if args.dry_run:
        for d in docs:
            print(f"would ingest {d}")
        return 0
    if not docs:
        print("nothing to ingest"); return 0

    failed = 0
    for d in docs:
        try:
            t = ingest(d, args.queue, args.reingest, labels.get(d))
            st = d.stat()
            ledger[labels.get(d, str(d))] = {
                "size": st.st_size, "mtime": int(st.st_mtime), "target": t.name,
            }
            print(f"ingested {d.name}\n  -> {t.relative_to(REPO)}")
        except OSError as exc:
            failed += 1
            hint = ("  (Google Docs cannot be read through the rclone mount - "
                    "use --remote gdrive: instead of --scan)") if exc.errno == 5 else ""
            print(f"FAILED {d.name}: {exc}{hint}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAILED {d.name}: {exc}", file=sys.stderr)
    LEDGER.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
