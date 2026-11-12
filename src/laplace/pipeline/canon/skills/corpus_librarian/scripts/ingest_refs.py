"""Bulk-ingest a per-project refs.bib into the global corpus.bib.

The corpus_librarian's mode 1, at volume. A project's own `refs.bib` carries
standard biblatex fields but none of the engine's distillation. This converts
each record into a corpus record: it regenerates the deterministic citekey
(lowercase firstauthor + year + first significant title word), preserves the
standard fields, and stamps the extension fields - `provenance` to the calling
project, `added`/`scout` for the trail, `status: unverified`.

The one thing it will NOT do is invent a `claim`. The distilled claim is the
load-bearing field (a wrong claim poisons every citing face), and it is an act of
grounded judgement, never a script's guess. So an ingested record enters with a
title-derived `tldr` and a `claim` left as an explicit `TODO` - visibly
incomplete, which `check_corpus` reports and a later distillation pass fills.
Ingestion never blocks; trust and completeness are promoted deliberately.

Deduplicates against the target by deterministic citekey, so re-running is safe
and two projects ingesting the same paper converge on one record (the duplicate
is reported, optionally gaining the new project in its `provenance`).

Stdlib-only. Usage:
    python ingest_refs.py <source-refs.bib> <target-corpus.bib> --project <key>
                          [--scout <name>] [--dry-run] [--update-provenance]
"""

import datetime
import os
import re
import sys

_STOPWORDS = {
    "a", "an", "the", "on", "of", "for", "and", "to", "in", "with", "without",
    "is", "are", "does", "do", "note", "study", "studies", "towards", "toward",
}
_ACCENTS = str.maketrans({
    "ä": "a", "ö": "o", "ü": "u", "é": "e", "è": "e", "ê": "e", "ë": "e",
    "á": "a", "à": "a", "í": "i", "ì": "i", "ó": "o", "ò": "o", "ú": "u",
    "ñ": "n", "ç": "c", "ø": "o", "å": "a", "š": "s", "ž": "z", "č": "c",
})


def read_safe(path):
    for enc in ("utf-8", "utf-16"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_records(text):
    """(raw_key, entry_type, {field: value}); the tolerant shared parse."""
    records = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        etype, key = m.group(1).strip(), m.group(2).strip()
        i = m.start() + text[m.start():].index("{") + 1
        depth, j = 1, i
        while j < len(text) and depth > 0:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[m.end():j - 1]
        fields = {}
        for fm in re.finditer(
            r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)", body
        ):
            fields[fm.group(1).strip().lower()] = fm.group(2).strip().strip("{}").strip('"').strip()
        records.append((key, etype, fields))
    return records


def _fold(s):
    # Strip LaTeX accent commands BEFORE removing braces, so {\v Z}unkovi{\v c}
    # folds to "zunkovic", not "vzunkovicv" (the caron 'v' must not glue on).
    s = re.sub(r"\\[a-zA-Z]+", "", s)       # \v \H \c \o ... (named accents/ligatures)
    s = re.sub(r"\\['\"^`~=.]", "", s)      # \' \" \^ \` \~ \= \. (symbol accents)
    s = re.sub(r"[{}\\'\"`^~]", "", s)      # any stray braces/marks left over
    return s.translate(_ACCENTS).lower()


def citekey(fields):
    """Deterministic: lowercase firstauthor surname + year + first significant
    title word. Matches corpus_librarian's CITEKEY pattern."""
    author = fields.get("author", "")
    first = re.split(r"\s+and\s+", author.strip())[0] if author else ""
    surname = first.split(",")[0].strip() if "," in first else first.strip().split(" ")[-1]
    surname = re.sub(r"[^a-z0-9]", "", _fold(surname)) or "anon"
    ym = re.search(r"\d{4}", fields.get("year", ""))
    year = ym.group(0) if ym else "0000"
    word = ""
    for raw in re.findall(r"[A-Za-z0-9]+", fields.get("title", "")):
        w = re.sub(r"[^a-z0-9]", "", _fold(raw))
        if w and w not in _STOPWORDS and not w.isdigit():
            word = w
            break
    word = word or "untitled"
    return f"{surname}{year}{word}"


def _tldr_from_title(fields):
    title = re.sub(r"\s+", " ", fields.get("title", "")).strip()
    return f"(auto, from title) {title}" if title else "(auto) untitled record - distil a tldr."


# Standard fields to carry through verbatim (others are dropped as project-local).
_CARRY = ["author", "title", "journal", "booktitle", "volume", "number", "pages",
          "year", "doi", "url", "note", "publisher"]


def render_record(key, etype, fields, project, scout, today):
    lines = [f"@{etype}{{{key},"]
    for f in _CARRY:
        if fields.get(f):
            lines.append(f"  {f:<10} = {{{fields[f]}}},")
    lines.append(f"  {'tldr':<10} = {{{_tldr_from_title(fields)}}},")
    lines.append(f"  {'claim':<10} = {{TODO: distil the single most citable proposition.}},")
    lines.append(f"  {'summary':<10} = {{TODO: write the essential 2-4 sentence summary (the accurate primitive).}},")
    lines.append(f"  {'status':<10} = {{unverified}},")
    lines.append(f"  {'cluster':<10} = {{}},")
    lines.append(f"  {'keywords':<10} = {{}},")
    lines.append(f"  {'relations':<10} = {{}},")
    lines.append(f"  {'provenance':<10} = {{{project}}},")
    lines.append(f"  {'added':<10} = {{{today}}},")
    lines.append(f"  {'scout':<10} = {{{scout}}},")
    lines.append("}")
    return "\n".join(lines)


def ingest(source, target, project, scout, dry_run, update_provenance):
    if not os.path.exists(source):
        print(f"Error: source {source} not found.", file=sys.stderr)
        return 2
    src_records = parse_records(read_safe(source))
    if not src_records:
        print("No records in source.", file=sys.stderr)
        return 2

    existing = {}
    target_text = ""
    if os.path.exists(target):
        target_text = read_safe(target)
        for k, _etype, _f in parse_records(target_text):
            existing[k] = _f

    today = datetime.date.today().isoformat()
    new_blocks, skipped, prov_updated = [], [], []
    seen_new = set()
    for _raw_key, etype, fields in src_records:
        key = citekey(fields)
        if key in existing or key in seen_new:
            skipped.append(key)
            if update_provenance and key in existing:
                provs = [p.strip() for p in (existing[key].get("provenance") or "").split(",") if p.strip()]
                if project not in provs:
                    prov_updated.append(key)
            continue
        seen_new.add(key)
        new_blocks.append(render_record(key, etype, fields, project, scout, today))

    print(f"# Ingest: {os.path.basename(source)} -> {os.path.basename(target)}")
    print(f"Source records: {len(src_records)} | new: {len(new_blocks)} | "
          f"already present (skipped): {len(skipped)}")
    if update_provenance and prov_updated:
        print(f"Provenance update needed for {len(prov_updated)} existing record(s): "
              f"{', '.join(sorted(prov_updated))}")
        print("  (run mode 3 / hand-append the project key - this script does not rewrite existing records.)")

    if dry_run:
        print("\n--dry-run: no file written. New records below.\n")
        print("\n\n".join(new_blocks))
        return 0
    if not new_blocks:
        print("Nothing new to ingest.")
        return 0

    block = "\n\n".join(new_blocks)
    header = "" if target_text.strip() else (
        "% The Laplace Engine - global literature corpus (corpus_librarian scheme).\n\n"
    )
    sep = "\n\n" if target_text.strip() else ""
    with open(target, "a", encoding="utf-8") as f:
        f.write(f"{header}{sep}% --- ingested from {os.path.basename(source)} "
                f"({project}, {today}) ---\n{block}\n")
    print(f"\nAppended {len(new_blocks)} record(s) to {target}.")
    print("Each entered as `status: unverified` with a TODO claim - run check_corpus to see "
          "them flagged incomplete, then distil claims deliberately. Ingestion never blocks.")
    return 0


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 2:
        print("Usage: python ingest_refs.py <source-refs.bib> <target-corpus.bib> "
              "--project <key> [--scout <name>] [--dry-run] [--update-provenance]",
              file=sys.stderr)
        return 2
    source, target = args[0], args[1]
    project = "unknown_project"
    scout = "eigen"
    if "--project" in argv:
        i = argv.index("--project")
        if i + 1 < len(argv):
            project = argv[i + 1]
    if "--scout" in argv:
        i = argv.index("--scout")
        if i + 1 < len(argv):
            scout = argv[i + 1]
    return ingest(source, target, project, scout,
                  dry_run="--dry-run" in argv, update_provenance="--update-provenance" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
