"""Global literature corpus completeness and consistency check.

(Sibling scripts in this skill: ``cluster_guide.py`` synthesises a per-cluster
state-of-the-art; ``ingest_refs.py`` bulk-imports a project ``refs.bib``;
``corpus_map.py`` prints the whole-store map + coverage worklist.)


Parses a corpus.bib in the corpus_librarian scheme and flags records that are not
yet well-formed: a missing required field, a status outside the allowed vocabulary,
a citekey off the deterministic pattern, a duplicate key, a relation of an unknown
type or pointing at a key not in the store, or (if keywords.yaml sits beside the
file) a cluster outside the controlled taxonomy.

Stdlib-only, regex-based, in the structured-ledger style of the other laplace scripts.
The point is a gate that never blocks ingestion but never lets a malformed record pass
silently - degrade loudly, never guess.
"""

import os
import re
import sys

# `summary` joins the required fields: the corpus is long-term memory, so the
# accurate primitive representation is part of being well-formed, not optional.
REQUIRED = ["title", "author", "year", "tldr", "claim", "summary", "status", "added", "scout"]
STATUS_VOCAB = {
    "unverified", "provisional", "borrowed", "contested", "established", "open-gap",
}
# The controlled relation vocabulary (mirrors corpus/keywords.yaml `relations`
# and graph._REL_TYPES). A relation of any other type is a malformed edge.
REL_TYPES = {
    "extends", "refines", "generalizes", "specializes", "contests", "corroborates",
    "applies", "tests", "motivates", "background_for", "analogue_of", "method_for",
    "reviews",
}
# partial:<restriction> is also allowed - matched separately.
PARTIAL = re.compile(r"^partial:\S+$", re.IGNORECASE)
PLACEHOLDER = re.compile(r"^\s*(tbd|todo|none|n/?a|pending|\?\?\?|)\s*$", re.IGNORECASE)
# A TODO claim/summary from bulk ingest is an incomplete record, not a present one.
TODO = re.compile(r"^\s*todo\b", re.IGNORECASE)
# Deterministic citekey: lowercase firstauthor + 4-digit year + title word.
# One sanctioned variant: a short author-initialism + year (e.g. `hgj2010` for
# Howgrave-Graham--Joux), admitted when a project face has already baked the
# initialism in as a citation contract (subset-sum-itqde projection plan,
# 2026-07-02). The initialism form carries no trailing title word.
CITEKEY = re.compile(r"^(?:[a-z][a-z0-9]*\d{4}[a-z0-9]+|[a-z]{2,4}\d{4})$")
REL_ENTRY = re.compile(r"([a-z_]+)\s*:\s*([^|]+?)\s*(?:\|.*)?$")


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
    """Return list of (citekey, {field: value}). Tolerant brace/quote field parse."""
    records = []
    for m in re.finditer(r"@\w+\s*\{\s*([^,\s]+)\s*,", text):
        key = m.group(1).strip()
        start = m.end()
        depth = 1
        i = m.start() + text[m.start():].index("{") + 1
        j = i
        while j < len(text) and depth > 0:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[start:j - 1]
        fields = {}
        for fm in re.finditer(
            r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)", body
        ):
            name = fm.group(1).strip().lower()
            val = fm.group(2).strip().strip("{}").strip('"').strip()
            fields[name] = val
        records.append((key, fields))
    return records


def parse_relations(raw):
    """(type, target) pairs from a relations field; descriptions stripped."""
    out = []
    for chunk in (raw or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = REL_ENTRY.match(chunk)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def _valid_clusters(path):
    """The controlled cluster labels from keywords.yaml beside the corpus, if any.
    Returns None when no taxonomy is found (then clusters are not checked)."""
    kp = os.path.join(os.path.dirname(os.path.abspath(path)), "keywords.yaml")
    if not os.path.exists(kp):
        return None
    try:
        import yaml

        data = yaml.safe_load(read_safe(kp)) or {}
    except Exception as exc:
        # The file is there but unreadable, so the cluster check is about to be
        # skipped. Say so: a silently skipped gate reads exactly like a passing
        # one, and a syntax error in the taxonomy would hide every bad cluster.
        print(f"Warning: {kp} exists but did not parse ({type(exc).__name__}: {exc}); "
              "cluster checking is OFF for this run.")
        return None
    clusters = set((data.get("clusters") or {}).keys())
    if not clusters:
        print(f"Warning: {kp} declares no clusters; cluster checking is OFF for this run.")
        return None
    return clusters


def check(path):
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        return 2
    records = parse_records(read_safe(path))
    if not records:
        print("No bib records found. Expected '@type{key, ...}' entries.")
        return 2

    valid_clusters = _valid_clusters(path)
    all_keys = {k for k, _ in records}

    incomplete, bad_status, bad_key, dupes = [], [], [], []
    bad_rel_type, dangling_rel, bad_cluster, thin = [], [], [], []
    seen = {}
    for key, fields in records:
        seen[key] = seen.get(key, 0) + 1
        missing = [
            f for f in REQUIRED
            if f not in fields or PLACEHOLDER.match(fields.get(f, "")) or TODO.match(fields.get(f, ""))
        ]
        if missing:
            incomplete.append((key, missing))
        status = fields.get("status", "").strip().lower()
        if status and status not in STATUS_VOCAB and not PARTIAL.match(status):
            bad_status.append((key, status))
        if not CITEKEY.match(key):
            bad_key.append(key)
        for rtype, tgt in parse_relations(fields.get("relations", "")):
            if rtype not in REL_TYPES:
                bad_rel_type.append((key, rtype))
            if tgt not in all_keys:
                dangling_rel.append((key, tgt))
        if valid_clusters is not None:
            for c in [c.strip() for c in (fields.get("cluster") or "").split(",") if c.strip()]:
                if c not in valid_clusters:
                    bad_cluster.append((key, c))
        if not (fields.get("relations") or "").strip():
            thin.append(key)
    dupes = [k for k, n in seen.items() if n > 1]

    n = len(records)
    print(f"# Corpus Check: {os.path.basename(path)}")
    print(
        f"Records: {n} | incomplete: {len(incomplete)} | bad-status: {len(bad_status)} | "
        f"off-pattern keys: {len(bad_key)} | duplicate keys: {len(dupes)} | "
        f"bad-relation-type: {len(bad_rel_type)} | dangling-relations: {len(dangling_rel)} | "
        f"bad-cluster: {len(bad_cluster)}"
    )
    print()

    def _section(title, rows, fmt):
        if rows:
            print(f"## {title}")
            for r in rows:
                print(fmt(r))
            print()

    _section("Incomplete records (missing/placeholder required field)", incomplete,
             lambda r: f"- `{r[0]}`: missing {', '.join(r[1])}")
    _section("Status outside the allowed vocabulary", bad_status,
             lambda r: f"- `{r[0]}`: '{r[1]}' (allowed: {', '.join(sorted(STATUS_VOCAB))}, partial:<r>)")
    _section("Citekeys off the deterministic pattern (firstauthor+year+word)", bad_key,
             lambda r: f"- `{r}`")
    _section("Duplicate citekeys", dupes, lambda r: f"- `{r}` x{seen[r]}")
    _section("Relations of an unknown type", bad_rel_type,
             lambda r: f"- `{r[0]}`: '{r[1]}' (allowed: {', '.join(sorted(REL_TYPES))})")
    _section("Relations pointing at a key not in the store", dangling_rel,
             lambda r: f"- `{r[0]}` -> `{r[1]}` (no such record)")
    _section("Clusters outside the controlled taxonomy (keywords.yaml)", bad_cluster,
             lambda r: f"- `{r[0]}`: '{r[1]}'")

    if thin:
        print(f"## Thin records (no relations - an unconnected primitive) [advisory]")
        print(f"- {len(thin)}: {', '.join('`'+k+'`' for k in thin)}")
        print()

    # Thin records are advisory (a primitive with no neighbours is weak, not
    # malformed); everything else is a hard defect the gate fails on.
    clean = not (incomplete or bad_status or bad_key or dupes
                 or bad_rel_type or dangling_rel or bad_cluster)
    if clean:
        msg = "Corpus is well-formed: records complete, statuses valid, keys unique and on-pattern, relations typed and resolved"
        msg += ", clusters in taxonomy." if valid_clusters is not None else "."
        print(msg)
        if thin:
            print(f"(Advisory: {len(thin)} record(s) carry no relations - consider connecting them.)")
    return 0 if clean else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_corpus.py <path_to_corpus.bib>")
        sys.exit(2)
    sys.exit(check(sys.argv[1]))
