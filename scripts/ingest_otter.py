"""ingest_otter.py - normalise an Otter export zip into a call skeleton in the intake queue.

THE OTTER PIPE (built 2026-08-20, his drop). Otter has no Linux desktop client - the
``otter_universal_latest.dmg`` in his Downloads is a macOS-only disk image and there is no
equivalent for this machine. The supported flow on Linux is therefore: record, then export
from the Otter web app, which drops a zip into ``~/Downloads``. This script is the other
half of that flow - it turns the drop into a call skeleton without a human touching it.

Given an Otter export zip it:

1. reads the ``*_transcript.txt`` and ``*_summary.txt`` members without extracting anything
   it was not asked for (no zip-slip: every member is resolved and checked under the target);
2. parses the meeting DATE (from the export filename, then the summary header, then the zip
   mtime) and the PARTICIPANTS (Otter's own speaker labels; real names where Otter attributed
   them, ``Speaker N`` placeholders counted but never invented into names);
3. writes ``evidence/intake_queue/call_<date>_<slug>/`` carrying the raw transcript, the raw
   summary, and a stub ``extraction.md`` whose header states what was parsed and - loudly -
   what was not.

It is DELIBERATELY not an extractor. It never calls a model, never guesses an attribution and
never writes a claim. The skeleton is a landing pad; a session reconstructs the extraction
from it against the house pattern (see ``evidence/call_2026-08-19_*/extraction.md``). The
whole point is that the raw survives the walk from Downloads to the repo unread and
unmodified, so nothing is lost before a mind gets to it.

Idempotent: re-running on the same zip refreshes the raws and leaves an existing
``extraction.md`` alone (an authored extraction is never overwritten by the machine).

Usage:
    scripts/laplace-python scripts/ingest_otter.py <export.zip> [<export.zip> ...]
    scripts/laplace-python scripts/ingest_otter.py --scan ~/Downloads

Exit codes: 0 all ingested (or nothing matched under --scan), 1 one or more failed.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QUEUE = REPO / "evidence" / "intake_queue"

# Otter's export filenames look like "2026-08-19_18_04_44 Note_transcript.txt" or plain
# "Note_transcript.txt" when the export carries no timestamp.
DATE_IN_NAME = re.compile(r"(20\d{2})[-_](\d{2})[-_](\d{2})")
TIME_IN_NAME = re.compile(r"20\d{2}[-_]\d{2}[-_]\d{2}[_ ](\d{2})[_-](\d{2})[_-](\d{2})")
# Summary header second line: "August 19, 2026"
DATE_IN_SUMMARY = re.compile(
    r"^\s*(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),\s*(20\d{2})\s*$",
    re.MULTILINE,
)
MONTHS = {
    m: i
    for i, m in enumerate(
        "January February March April May June July August September October "
        "November December".split(),
        start=1,
    )
}
# Transcript speaker lines: "Will Handley  00:03" / "Speaker 3  12:23" / "Unknown Speaker  1:22:00"
SPEAKER_LINE = re.compile(r"^(?P<who>[^\d\n][^\n]{0,60}?)\s{2,}(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\s*$")
PLACEHOLDER = re.compile(r"^(speaker\s*\d+|unknown speaker)$", re.IGNORECASE)

STOPWORDS = {"note", "otter", "ai", "transcript", "summary", "recording", "meeting", "call", "new"}


def slugify(text: str, fallback: str = "untitled") -> str:
    """Lowercase hyphen slug, stopwords dropped, capped at four words."""
    words = [w for w in re.split(r"[^A-Za-z0-9]+", text.lower()) if w and w not in STOPWORDS]
    words = [w for w in words if not w.isdigit()]
    return "-".join(words[:4]) or fallback


def _members(zf: zipfile.ZipFile) -> tuple[str | None, str | None]:
    """Return (transcript_member, summary_member); either may be None."""
    transcript = summary = None
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        low = name.lower()
        if low.endswith("_transcript.txt") or (transcript is None and low.endswith("transcript.txt")):
            transcript = name
        elif low.endswith("_summary.txt") or (summary is None and low.endswith("summary.txt")):
            summary = name
    return transcript, summary


def _read(zf: zipfile.ZipFile, member: str | None) -> str:
    if member is None:
        return ""
    return zf.read(member).decode("utf-8", errors="replace")


def parse_date(zip_path: Path, member_names: list[str], summary: str) -> tuple[str, str]:
    """Return (iso_date, provenance) - filename, then summary header, then zip mtime."""
    for candidate in [zip_path.name, *member_names]:
        m = DATE_IN_NAME.search(candidate)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", f"export filename ({candidate})"
    m = DATE_IN_SUMMARY.search(summary)
    if m:
        return (
            f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}",
            "Otter summary header",
        )
    mtime = _dt.datetime.fromtimestamp(zip_path.stat().st_mtime)
    return mtime.strftime("%Y-%m-%d"), "zip mtime (WEAK - export time, not meeting time)"


def parse_start_time(zip_path: Path, member_names: list[str]) -> str | None:
    for candidate in [zip_path.name, *member_names]:
        m = TIME_IN_NAME.search(candidate)
        if m:
            return f"{m.group(1)}:{m.group(2)}:{m.group(3)}"
    return None


def parse_speakers(transcript: str) -> tuple[list[str], list[str]]:
    """Return (named_speakers, placeholder_labels), each ordered by first appearance."""
    named: list[str] = []
    placeholders: list[str] = []
    for line in transcript.splitlines():
        m = SPEAKER_LINE.match(line.rstrip())
        if not m:
            continue
        who = m.group("who").strip()
        bucket = placeholders if PLACEHOLDER.match(who) else named
        if who not in bucket:
            bucket.append(who)
    return named, placeholders


def parse_duration(transcript: str) -> str | None:
    stamps = [m.group("ts") for line in transcript.splitlines() if (m := SPEAKER_LINE.match(line.rstrip()))]
    return stamps[-1] if stamps else None


def parse_title(summary: str, zip_path: Path) -> str:
    first = next((ln.strip() for ln in summary.splitlines() if ln.strip()), "")
    return first or zip_path.stem


def stub_extraction(meta: dict) -> str:
    named = meta["named"]
    placeholders = meta["placeholders"]
    if named and placeholders:
        who = (
            f"Otter attributed **{', '.join(named)}** by name and left "
            f"**{len(placeholders)}** unattributed label(s) ({', '.join(placeholders)})."
        )
    elif named:
        who = f"Otter attributed **{', '.join(named)}** by name; no placeholder labels."
    elif placeholders:
        who = (
            f"Otter attributed **nobody** by name. {len(placeholders)} placeholder label(s): "
            f"{', '.join(placeholders)}."
        )
    else:
        who = "No speaker lines parsed - check the raw before assuming the format."

    started = f" (recording started {meta['start_time']})" if meta["start_time"] else ""
    return f"""# Extraction — TITLE ME ({meta['date']})

<!-- STUB written by scripts/ingest_otter.py at {meta['ingested_at']}. Everything below the
     PARSED block is a prompt, not a finding. Reconstruct the extraction against the house
     pattern (evidence/call_2026-08-19_techspert-requirements/extraction.md), then move this
     directory out of evidence/intake_queue/ to evidence/call_<date>_<slug>/. -->

**SOURCE QUALITY WARNING.** This is a **low-quality Otter transcript**. Otter mis-attributes
speakers, invents phantom speakers out of background noise, garbles technical vocabulary, and
**has no ear for irony** — any tone-dependent reading is UNCERTAIN and must not be quoted
outward. Otter's own summary invents attributions; treat it as untrusted. Speaker numbering is
**not stable across files** from the same meeting. Flag uncertain attribution explicitly rather
than guessing it.

## PARSED (machine, no inference)

- **Source zip:** `{meta['zip_name']}`
- **Meeting date:** {meta['date']} — from {meta['date_provenance']}{started}
- **Otter title:** {meta['title']}
- **Speakers:** {who}
- **Last timestamp in transcript:** {meta['duration'] or 'none parsed'}
- **Raw:** [{meta['transcript_file']}]({meta['transcript_file']}) · [{meta['summary_file']}]({meta['summary_file']})

## TO RECONSTRUCT (delete each heading you answer)

- **Who was actually present**, and which real name maps to which `Speaker N`. If it cannot be
  determined from the audio, say so — do not guess.
- **Verbatim asks and commitments**, with attribution, uncertain ones marked UNCERTAIN.
- **Decisions** taken, and by whom.
- **Dates and clocks** — every deadline, window, or cadence named.
- **Product-shaping facts** — what this changes about what gets built.
- **Numbers spoken**, checked against the banked runs. Score discipline: one canonical
  statement, said once.
- **PERIMETER** — third-party personal data, sealed spans, and anything that must not travel
  into a derived artifact.
- **Flags** for the next decision point.
"""


def ingest(zip_path: Path, queue: Path = QUEUE) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        transcript_member, summary_member = _members(zf)
        if transcript_member is None:
            raise ValueError(f"no *_transcript.txt member in {zip_path.name}")
        transcript = _read(zf, transcript_member)
        summary = _read(zf, summary_member)
        member_names = [n for n in (transcript_member, summary_member) if n]

    date, date_provenance = parse_date(zip_path, member_names, summary)
    title = parse_title(summary, zip_path)
    named, placeholders = parse_speakers(transcript)

    slug = slugify("-".join(named[:3])) if named else ""
    if not slug:
        slug = slugify(title, fallback="unattributed")
    target = queue / f"call_{date}_{slug}"
    target.mkdir(parents=True, exist_ok=True)

    # Never clobber a prior ingest of a DIFFERENT recording into the same slug: suffix instead.
    transcript_file = "transcript_otter.md"
    summary_file = "otter_summary.md"
    existing = target / transcript_file
    if existing.exists() and existing.read_text(encoding="utf-8", errors="replace") != transcript:
        n = 2
        while (target / f"transcript_otter_{n}.md").exists():
            n += 1
        transcript_file = f"transcript_otter_{n}.md"
        summary_file = f"otter_summary_{n}.md"

    (target / transcript_file).write_text(transcript, encoding="utf-8")
    if summary:
        (target / summary_file).write_text(summary, encoding="utf-8")

    meta = {
        "zip_name": zip_path.name,
        "date": date,
        "date_provenance": date_provenance,
        "start_time": parse_start_time(zip_path, member_names),
        "title": title,
        "named": named,
        "placeholders": placeholders,
        "duration": parse_duration(transcript),
        "transcript_file": transcript_file,
        "summary_file": summary_file if summary else "(no summary in export)",
        "ingested_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }

    stub = target / "extraction.md"
    if not stub.exists():
        stub.write_text(stub_extraction(meta), encoding="utf-8")
        note = "wrote stub extraction.md"
    else:
        note = "kept existing extraction.md (authored work is never overwritten)"

    try:
        shown = target.relative_to(REPO)
    except ValueError:  # queue pointed outside the repo (tests, dry runs)
        shown = target
    print(f"[ingest_otter] {zip_path.name} -> {shown} ({note})")
    print(f"[ingest_otter]   date={date} via {date_provenance}; "
          f"named={named or 'none'}; placeholders={len(placeholders)}")
    return target


def _ledger_key(p: Path) -> str:
    st = p.stat()
    return f"{p.resolve()}::{st.st_size}::{int(st.st_mtime)}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zips", nargs="*", type=Path, help="Otter export zip(s)")
    ap.add_argument("--scan", type=Path, help="directory to scan for *otter*.zip / *Note_otter_ai*.zip")
    ap.add_argument("--queue", type=Path, default=QUEUE, help="target queue directory")
    ap.add_argument("--reingest", action="store_true", help="ignore the seen-ledger under --scan")
    args = ap.parse_args(argv)

    targets = list(args.zips)
    scanned: list[Path] = []
    if args.scan:
        hits: set[Path] = set()
        for pat in ("*otter*.zip", "*Otter*.zip", "*Note_otter_ai*.zip"):
            hits.update(args.scan.glob(pat))  # the globs overlap; count each file once
        scanned = sorted(hits)

    # The seen-ledger exists so the path watcher can fire on every Downloads change without
    # re-walking the whole directory. Keyed on path+size+mtime, so a re-export of the same
    # meeting IS picked up while an untouched file is not. Explicit zips bypass it entirely.
    ledger_path = args.queue / ".ingested.json"
    ledger: dict[str, str] = {}
    if args.scan and not args.reingest and ledger_path.exists():
        try:
            import json

            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a corrupt ledger must never block an ingest
            ledger = {}
    fresh = [p for p in scanned if args.reingest or _ledger_key(p) not in ledger]
    skipped = len(scanned) - len(fresh)
    targets.extend(fresh)

    # de-dup, preserve order
    seen: set[Path] = set()
    ordered = [p for p in targets if not (p.resolve() in seen or seen.add(p.resolve()))]

    if not ordered:
        print(f"[ingest_otter] nothing to ingest ({skipped} already-seen zip(s) skipped)")
        return 0

    failures = 0
    for zip_path in ordered:
        try:
            ingest(zip_path, args.queue)
            if args.scan:
                ledger[_ledger_key(zip_path)] = _dt.datetime.now().isoformat(timespec="seconds")
        except Exception as exc:  # noqa: BLE001 - a bad drop must not take the watcher down
            failures += 1
            print(f"[ingest_otter] FAILED {zip_path}: {exc}", file=sys.stderr)

    if args.scan:
        import json

        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(ledger, indent=1, sort_keys=True), encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
