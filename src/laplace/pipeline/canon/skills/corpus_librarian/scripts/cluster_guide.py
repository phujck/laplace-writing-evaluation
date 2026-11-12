"""Synthesise an ephemeral cluster guide from the global corpus.

The corpus_librarian's mode 2, made into a backing script. Given a cluster label
(or a concept query matched against `cluster`/`keywords`), read the matching
records, group them by trust status, sort the chronological spine by year, and
emit the three-part state-of-the-art: where the field is now (established),
how it got here (the spine), and where it could go next (open gaps + the records
still pending trust). The novelty boundary for a project is what its own
`provenance` does *not* yet cite in the cluster.

The guide is EPHEMERAL - generated and handed to drafting as context, never
stored. `corpus.bib` is the only persistent artifact. The trust boundary holds:
only `established` records are reported as settled support; provisional, borrowed,
and unverified records surface as candidates, never as fact.

Stdlib-only, regex-based, the structured-ledger style of the other laplace
scripts. Shares its bib parser with check_corpus (one store, one reading).

Usage:
    python cluster_guide.py <corpus.bib> <cluster-or-query> [--project <key>]
"""

import os
import re
import sys

REQUIRED_TRUST = "established"
SETTLED = {"established"}
CANDIDATE = {"provisional", "borrowed", "unverified", "contested"}
PARTIAL = re.compile(r"^partial:\S+$", re.IGNORECASE)


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
    """(citekey, {field: value}); the same tolerant parse check_corpus uses."""
    records = []
    for m in re.finditer(r"@\w+\s*\{\s*([^,\s]+)\s*,", text):
        key = m.group(1).strip()
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
        records.append((key, fields))
    return records


def _tokens(field):
    return [t.strip().lower() for t in (field or "").split(",") if t.strip()]


def matches(fields, query):
    """A record is in the cluster if the query is one of its cluster labels, or
    (looser) appears among its keywords. Cluster match is preferred and reported."""
    q = query.strip().lower()
    if q in _tokens(fields.get("cluster")):
        return "cluster"
    if q in _tokens(fields.get("keywords")):
        return "keyword"
    return None


def _year(fields):
    m = re.search(r"\d{4}", fields.get("year", ""))
    return int(m.group(0)) if m else 0


def guide(path, query, project=None):
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        return 2
    records = parse_records(read_safe(path))
    if not records:
        print("No bib records found.")
        return 2

    hits = []
    for key, f in records:
        how = matches(f, query)
        if how:
            hits.append((key, f, how))
    if not hits:
        print(f"# Cluster guide: {query}\n\nNo records match this cluster or keyword. "
              f"The cluster is empty - a finding: the literature face must be carried by "
              f"derivation or numerics, or the query is mis-spelled.")
        return 1

    settled = [(k, f) for k, f, _ in hits if (f.get("status", "").lower() in SETTLED)]
    candidates = [(k, f) for k, f, _ in hits
                  if f.get("status", "").lower() in CANDIDATE
                  or PARTIAL.match(f.get("status", "").lower() or "")]
    gaps = [(k, f) for k, f, _ in hits if f.get("status", "").lower() == "open-gap"]
    spine = sorted(hits, key=lambda r: (_year(r[1]), r[0]))

    print(f"# Cluster guide: {query}")
    print(f"\n{len(hits)} record(s) | established: {len(settled)} | "
          f"candidates pending trust: {len(candidates)} | open gaps: {len(gaps)}")
    print("\n*Ephemeral synthesis - not stored. Only `established` records are settled "
          "support; the rest are candidates pending the author's promotion.*")

    print("\n## Where the field is now (established)")
    if settled:
        for k, f in sorted(settled, key=lambda r: -_year(r[1])):
            print(f"- **{k}** ({f.get('year','?')}): {f.get('claim') or f.get('tldr') or '(no claim)'}")
    else:
        print("- *Nothing established yet. Every claim below is a candidate - the field's "
              "settled support in this cluster is, honestly, empty.*")

    print("\n## How it got here (chronological spine)")
    for k, f, how in spine:
        tag = "" if how == "cluster" else " _(keyword match)_"
        print(f"- {f.get('year','?')} — **{k}** [{f.get('status','?')}]{tag}: "
              f"{f.get('tldr') or f.get('claim') or ''}")

    print("\n## Where it could go next (candidates + open gaps)")
    if candidates:
        print("\n**Candidates pending trust** (usable, visibly untrusted):")
        for k, f in sorted(candidates, key=lambda r: -_year(r[1])):
            print(f"- **{k}** [{f.get('status','?')}]: {f.get('claim') or f.get('tldr') or ''}")
    if gaps:
        print("\n**Open gaps:**")
        for k, f in gaps:
            print(f"- **{k}**: {f.get('claim') or f.get('tldr') or ''}")
    if not candidates and not gaps:
        print("- No candidates or open gaps recorded in this cluster.")

    if project:
        cited = [k for k, f, _ in hits if project.strip().lower() in _tokens(f.get("provenance"))]
        uncited = [k for k, f, _ in hits if k not in cited]
        print(f"\n## Novelty boundary for `{project}`")
        print(f"Already cited by this project ({len(cited)}): "
              f"{', '.join(sorted(cited)) or '(none)'}")
        print(f"In the cluster but NOT yet cited here ({len(uncited)}): "
              f"{', '.join(sorted(uncited)) or '(none)'}  "
              f"— the literature this project has not yet placed itself against.")
    return 0


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 2:
        print("Usage: python cluster_guide.py <corpus.bib> <cluster-or-query> [--project <key>]",
              file=sys.stderr)
        return 2
    project = None
    if "--project" in argv:
        idx = argv.index("--project")
        if idx + 1 < len(argv):
            project = argv[idx + 1]
    return guide(args[0], args[1], project)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
