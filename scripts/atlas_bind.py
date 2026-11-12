#!/usr/bin/env python3
"""atlas_bind.py — conjugate-view binding for a diagram atlas.

Two channels, both loud:

  machine -> human   staleness.  Every diagram's citations are fingerprinted at
                     bind time.  `check` recomputes and says FRESH / MOVED /
                     STALE, so a drawing announces when the ground it stands on
                     has shifted.

  human -> machine   redlines.   A correction from the author banks as a typed
                     row.  It stays open until somebody consumes it, and `check`
                     counts open rows beside the staleness state, because an
                     unconsumed correction is drift in the other direction.

Stdlib only.  No network.  No clock reads: every timestamp enters through an
explicit --stamp, because this is reconstruction machinery and the house forbids
machinery that quietly disagrees with itself between two runs.
"""

import argparse
import hashlib
import json
import os
import re
import sys

# scripts/atlas_bind.py -> repo root is one level up.  `check` resolves cites
# against wherever this checkout actually lives, never against a bound
# --source-root from a possibly-decommissioned machine; that bound value is
# kept only as provenance in the header, and an explicit --source-root always
# overrides both.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOOL = "atlas_bind"
TOOL_VERSION = "1"
INDEX_NAME = "atlas_index.json"
REDLINES_NAME = "redlines.jsonl"
INDEX_SCHEMA = "atlas.index/1"
CHECK_SCHEMA = "atlas.check/1"
REDLINE_SCHEMA = "atlas.redline/1"
REDLINES_REPORT_SCHEMA = "atlas.redlines/1"

WINDOW = 3  # +/- lines of context around a cited span
VALID_AUDIENCES = ("ROOM-SAFE", "INTERNAL")

# A directory name that implies an audience seal.  A ROOM-SAFE drawing filed
# under internal/ is merely conservative; an INTERNAL drawing filed under room/
# is a leak, so the mismatch is surfaced rather than smoothed.
DIR_AUDIENCE_HINT = {"room": "ROOM-SAFE", "internal": "INTERNAL"}

STAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)

# `path:12-34`, `path:12`, `path:12-34,56`, `path:12,34-56,78` (comma multi-cite:
# several spans into the same file behind one citation).
LINECITE_RE = re.compile(
    r"^(?P<path>[^\s:`]+):(?P<spans>\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)$"
)
SPAN_RE = re.compile(r"(?P<a>\d+)(?:-(?P<b>\d+))?")
# something that could be a path: has a separator, or a short extension
PATHISH_RE = re.compile(r"(?:/)|(?:\.[A-Za-z0-9]{1,6}$)")
BACKTICK_RE = re.compile(r"`([^`]+)`")
# bare (un-backticked) file:line tokens, for tolerance.  The comma multi-cite
# form is matched WHOLE: a pattern that stopped at the first span would hand
# classify_token a truncated token and drop the trailing spans in silence —
# exactly the failure the backticked form had (WO-20260817-comma-multicite-parser).
LOOSE_RE = re.compile(
    r"(?<![`\w/.-])([A-Za-z0-9_.\-/]+\.[A-Za-z0-9]{1,6}:\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)"
)

TITLE_RE = re.compile(r"^#\s+(.*\S)\s*$")
FIELD_RE = re.compile(r"^\s*[*_]{0,2}(?P<key>[A-Za-z][A-Za-z \-]*?)[*_]{0,2}\s*:\s*(?P<val>.*)$")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(?P<body>.*)$")
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
HEADING_RE = re.compile(r"^\s*#{1,6}\s")


class BindError(Exception):
    pass


# ---------------------------------------------------------------- hashing ----

def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def read_lines(path):
    """Decode and split, normalising line endings so a CRLF round trip does not
    masquerade as a content change."""
    raw = read_bytes(path)
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [ln[:-1] if ln.endswith("\r") else ln for ln in lines]


def window_bounds(a, b, n_lines):
    """1-based inclusive window of +/-WINDOW lines around span a..b, clipped."""
    start = max(1, a - WINDOW)
    end = min(n_lines, b + WINDOW)
    if end < start:
        end = start
    return start, end


def hash_window(lines, start, end):
    """Hash lines[start-1:end] (1-based inclusive)."""
    chunk = lines[start - 1:end]
    return sha256_bytes("\n".join(chunk).encode("utf-8"))


def all_window_hashes(lines, length):
    """Map every window of `length` lines to its 1-based start offsets."""
    out = {}
    if length <= 0 or length > len(lines):
        return out
    for start in range(1, len(lines) - length + 2):
        h = hash_window(lines, start, start + length - 1)
        out.setdefault(h, []).append(start)
    return out


# ---------------------------------------------------------------- parsing ----

def strip_edges(tok):
    return tok.strip().strip('"\'()[],;').rstrip(".,;:").strip()


def classify_token(tok):
    """Sort a candidate token into one of three buckets.

    line   an explicit file:line, file:start-end, or comma multi-cite
           (file:a-b,c,d-e — several spans into the same file behind one
           citation) citation.  The `:line` suffix is a declaration of intent
           to cite, so it is held strictly: if the file is missing, that is a
           bind error.  parsed is (path, [(a, b), ...]) — one or more spans.
    bare   a bare path with no line span.  Held leniently, because bullets are
           full of backticked prose (`node_forms`, `verdict`, `promises.jsonl`)
           that looks pathlike and is not a citation.  Resolves -> citation;
           does not resolve -> ignored and recorded, never an error.
    None   not a citation candidate at all.
    """
    tok = strip_edges(tok)
    if not tok or " " in tok or "\t" in tok:
        return None, None
    m = LINECITE_RE.match(tok)
    if m:
        spans = []
        for sm in SPAN_RE.finditer(m.group("spans")):
            a = int(sm.group("a"))
            b = int(sm.group("b")) if sm.group("b") else a
            if b < a:
                a, b = b, a
            spans.append((a, b))
        return "line", (m.group("path"), spans)
    if tok.endswith("/"):
        return None, None
    if ":" in tok:
        return None, None
    if PATHISH_RE.search(tok):
        return "bare", (tok, None, None)
    return None, None


def scan_citations(bullet_text):
    """Pull citation candidates out of one Sources bullet, in order, deduped.

    A `line` token may expand into several citations (one per comma-separated
    span, same path, same raw text) — each still checked/fingerprinted as an
    ordinary single-span line citation downstream.
    """
    found = []
    seen = set()
    cands = list(BACKTICK_RE.findall(bullet_text))
    cands.extend(LOOSE_RE.findall(bullet_text))
    for tok in cands:
        kind, parsed = classify_token(tok)
        if kind is None:
            continue
        raw = strip_edges(tok)
        if kind == "line":
            path, spans = parsed
            for a, b in spans:
                key = ("line", path, a, b)
                if key in seen:
                    continue
                seen.add(key)
                found.append({"kind": "line", "raw": raw, "path": path,
                              "line_start": a, "line_end": b})
        else:
            path = parsed[0]
            key = (kind, path, None, None)
            if key in seen:
                continue
            seen.add(key)
            found.append({"kind": kind, "raw": raw, "path": path,
                          "line_start": None, "line_end": None})
    return found


def parse_diagram(path):
    """Parse one diagram .md into title / audience / citations.

    Tolerant by construction: the landed atlas puts citations at the head of a
    bullet in some files and at the tail in others, sometimes several to a
    bullet, sometimes none.  So the Sources block is read as bullets and each
    whole bullet is scanned.
    """
    lines = read_lines(path)
    title = None
    audience = None
    citations = []
    ignored = []
    problems = []

    for ln in lines:
        m = TITLE_RE.match(ln)
        if m:
            title = m.group(1).strip()
            break

    in_sources = False
    in_fence = False
    bullet = None
    bullets = []

    def flush():
        if bullet is not None:
            bullets.append(" ".join(bullet))

    for ln in lines:
        if FENCE_RE.match(ln):
            if in_sources:
                in_sources = False
                flush()
                bullet = None
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        if not in_sources:
            fm = FIELD_RE.match(ln)
            if fm:
                key = fm.group("key").strip().lower()
                val = fm.group("val").strip().strip("*_` ")
                if key == "audience" and audience is None:
                    audience = val.upper()
                    continue
                if key == "sources":
                    in_sources = True
                    bullet = None
                    if val:
                        bullet = [val]
                    continue
            continue

        # inside the Sources block
        if HEADING_RE.match(ln):
            flush()
            bullet = None
            in_sources = False
            continue
        bm = BULLET_RE.match(ln)
        if bm:
            flush()
            bullet = [bm.group("body")]
            continue
        if ln.strip() == "":
            continue
        if bullet is not None:
            bullet.append(ln.strip())
        # a non-bullet, non-blank line with no open bullet ends the block
        elif ln.strip():
            in_sources = False
    flush()

    for b in bullets:
        for c in scan_citations(b):
            citations.append(c)

    if title is None:
        problems.append("no `# title` line found")
    audience_note = None
    if audience is None:
        problems.append("no `Audience:` line found")
    elif audience not in VALID_AUDIENCES:
        # A scoped audience line ("ROOM-SAFE (Friday...) — diagram and caption
        # only...") carries a valid token as its prefix; keep the remainder as
        # the scope note rather than refusing the seal's own wording.
        for tok in VALID_AUDIENCES:
            if audience.startswith(tok) and (len(audience) == len(tok) or not audience[len(tok)].isalnum()):
                audience_note = audience[len(tok):].strip(" -\u2014(").rstrip(")")
                audience = tok
                break
        else:
            problems.append("audience %r is not one of %s" % (audience, "|".join(VALID_AUDIENCES)))
    if not citations:
        problems.append("no resolvable citations found in the Sources block")

    return {"title": title, "audience": audience, "audience_note": audience_note,
            "citations": citations, "ignored": ignored, "problems": problems}


# ------------------------------------------------- manifest surfaces mode ----
# The generalization (2026-08-23, the accounting day, SB-3): the same bind/check
# discipline over ANY claim-bearing surface, not only diagrams/. The surface list
# is FROZEN in a manifest file (one repo-relative path per line, optional
# `boxstate` tag for surfaces asserting box facts); the index lives beside it as
# `<manifest>.index.json`. Surfaces are scanned WHOLE-DOC (citations ride prose,
# not a Sources block), and the vocabulary grows ONE state: a `boxstate` surface
# whose claims ground ONLY in line-span hashes is UNGROUNDED -- hash freshness
# detects file drift and is structurally blind to intent-banked-as-fact; box
# claims need executable checks, declared inline as `check: <command>` tokens.

CHECK_DECL_RE = re.compile(r"`check:\s*([^`]+)`")


def parse_surface(path):
    """Whole-document parse: every non-fence line scanned for citations."""
    lines = read_lines(path)
    title = None
    citations, ignored = [], []
    n_checks = 0
    in_fence = False
    seen = set()
    for ln in lines:
        if FENCE_RE.match(ln):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if title is None:
            m = TITLE_RE.match(ln)
            if m:
                title = m.group(1).strip()
        n_checks += len(CHECK_DECL_RE.findall(ln))
        for c in scan_citations(ln):
            key = (c["kind"], c["path"], c["line_start"], c["line_end"])
            if key not in seen:
                seen.add(key)
                citations.append(c)
    return {"title": title, "citations": citations, "ignored": ignored,
            "executable_checks": n_checks, "problems": []}


def read_manifest(manifest):
    rows = []
    with open(manifest, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            parts = ln.split()
            rows.append({"path": parts[0], "boxstate": "boxstate" in parts[1:]})
    return rows


def manifest_index_path(manifest):
    return manifest + ".index.json"


def bind_manifest(args):
    manifest = os.path.abspath(args.manifest)
    if not os.path.isfile(manifest):
        die("manifest not found: %s" % manifest)
    if not STAMP_RE.match(args.stamp):
        die("--stamp must be ISO 8601, got %r" % args.stamp)
    source_root = os.path.abspath(args.source_root) if args.source_root else REPO_ROOT
    surfaces = {}
    errors = []
    for row in read_manifest(manifest):
        target = os.path.join(source_root, row["path"])
        if not os.path.isfile(target):
            errors.append("%s: surface does not exist" % row["path"])
            continue
        parsed = parse_surface(target)
        cits = []
        for cit in parsed["citations"]:
            fp, err = fingerprint_citation(cit, source_root)
            if err:
                # surfaces cite in dialects (basename spans, third-party paths);
                # an unresolvable line cite is a recorded verdict here, not a
                # bind refusal -- the check will keep serving it as STALE.
                cits.append({"raw": cit["raw"], "kind": cit["kind"], "path": cit["path"],
                             "line_start": cit["line_start"], "line_end": cit["line_end"],
                             "unresolved_at_bind": err})
            elif fp is not None:
                cits.append(fp)
            else:
                parsed["ignored"].append(cit["raw"])
        surfaces[row["path"]] = {
            "file": row["path"], "title": parsed["title"], "boxstate": row["boxstate"],
            "executable_checks": parsed["executable_checks"], "citations": cits,
            "ignored_barewords": sorted(set(parsed["ignored"])),
        }
    if errors:
        for e in errors:
            sys.stderr.write("  %s\n" % e)
        die("bind --manifest failed: %d missing surface(s)" % len(errors))
    index = {"schema": INDEX_SCHEMA + "+surfaces", "tool": TOOL,
             "tool_version": TOOL_VERSION, "bound_at": args.stamp,
             "manifest": manifest, "source_root": source_root,
             "window_context_lines": WINDOW, "surfaces": surfaces}
    out = manifest_index_path(manifest)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, sort_keys=True)
        fh.write("\n")
    n_cit = sum(len(s["citations"]) for s in surfaces.values())
    print("bound %d surface(s), %d citation(s)" % (len(surfaces), n_cit))
    print("index       %s" % out)
    return 0


def check_manifest(args):
    manifest = os.path.abspath(args.manifest)
    ipath = manifest_index_path(manifest)
    if not os.path.isfile(ipath):
        die("no index beside manifest — run `bind --manifest` first")
    with open(ipath, encoding="utf-8") as fh:
        index = json.load(fh)
    source_root = os.path.abspath(args.source_root) if args.source_root else REPO_ROOT
    rows = []
    worst = 0
    for key in sorted(index["surfaces"]):
        s = index["surfaces"][key]
        cits = []
        for c in s["citations"]:
            if "unresolved_at_bind" in c:
                cits.append({**c, "state": "STALE",
                             "reason": "unresolved since bind: " + c["unresolved_at_bind"]})
            else:
                cits.append(check_citation(c, source_root))
        # THE POST-BIND RE-SCAN (the judge's plant killed the first form, 2026-08-23):
        # check mode used to verify ONLY citations bound at index time, so a claim ADDED
        # after the freeze was never checked - new lies rode free while old truths rotted
        # loudly. The document re-scans NOW; any citation absent from the bound set
        # stamps NEW-UNVERIFIED and fails the check until the next bind adjudicates it.
        bound = {(c.get("path"), c.get("line_start"), c.get("line_end"))
                 for c in s["citations"]}
        live_path = os.path.join(source_root, key)
        if os.path.isfile(live_path):
            for cit in parse_surface(live_path)["citations"]:
                k = (cit["path"], cit["line_start"], cit["line_end"])
                if k not in bound:
                    cits.append({**cit, "state": "NEW-UNVERIFIED",
                                 "reason": "cited after the bind - unverified until the "
                                           "next bind fingerprints it"})
        states = [c["state"] for c in cits]
        state = ("STALE" if "STALE" in states else
                 "NEW-UNVERIFIED" if "NEW-UNVERIFIED" in states else
                 "MOVED" if "MOVED" in states else "FRESH")
        ungrounded = bool(s.get("boxstate")) and s.get("executable_checks", 0) == 0
        rows.append({"file": key, "state": state, "ungrounded": ungrounded,
                     "executable_checks": s.get("executable_checks", 0),
                     "boxstate": bool(s.get("boxstate")),
                     "counts": {st: states.count(st)
                                for st in ("FRESH", "MOVED", "STALE", "NEW-UNVERIFIED")},
                     "worst": [c for c in cits if c["state"] != "FRESH"][:3]})
        if state != "FRESH" or ungrounded:
            worst = 1
    n_ung = sum(1 for r in rows if r["ungrounded"])
    report = {"schema": CHECK_SCHEMA + "+surfaces", "bound_at": index["bound_at"],
              "surfaces": rows, "ungrounded": n_ung,
              "vocabulary": ["FRESH", "MOVED", "STALE", "UNGROUNDED", "NEW-UNVERIFIED"]}
    if getattr(args, "json", False):
        print(json.dumps(report, indent=1, sort_keys=True))
    else:
        for r in rows:
            flag = " UNGROUNDED" if r["ungrounded"] else ""
            c = r["counts"]
            print("%-28s %-6s%s  %d/%d/%d  checks=%d"
                  % (r["file"], r["state"], flag, c["FRESH"], c["MOVED"], c["STALE"],
                     r["executable_checks"]))
        tot = {st: sum(r["counts"][st] for r in rows)
               for st in ("FRESH", "MOVED", "STALE", "NEW-UNVERIFIED")}
        bound_tot = tot["FRESH"] + tot["MOVED"] + tot["STALE"]
        print("%d surface(s): %d UNGROUNDED — bound citations %d = %d FRESH + %d MOVED + "
              "%d STALE, +%d NEW-UNVERIFIED post-bind — exit %d"
              % (len(rows), n_ung, bound_tot, tot["FRESH"], tot["MOVED"],
                 tot["STALE"], tot["NEW-UNVERIFIED"], worst))
    return worst


def find_diagrams(diagrams_dir):
    out = []
    for root, dirs, files in os.walk(diagrams_dir):
        dirs.sort()
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in sorted(files):
            if fn in ("ATLAS.md", "README.md"):
                continue  # the index and its kin document the atlas; they are not drawings
            if fn.endswith(".md") and not fn.startswith("."):
                if fn.upper().startswith("ATLAS_TEMPLATE"):
                    continue
                out.append(os.path.join(root, fn))
    return out


def rel(path, base):
    return os.path.relpath(path, base).replace(os.sep, "/")


def dir_hint(rel_path):
    head = rel_path.split("/")[0].lower() if "/" in rel_path else ""
    return DIR_AUDIENCE_HINT.get(head)


# ------------------------------------------------------------------- bind ----

def fingerprint_citation(cit, source_root):
    """Resolve and fingerprint one citation.  Returns (row, error_or_None)."""
    target = os.path.normpath(os.path.join(source_root, cit["path"]))
    row = {
        "raw": cit["raw"],
        "kind": cit["kind"],
        "path": cit["path"],
        "line_start": cit["line_start"],
        "line_end": cit["line_end"],
    }
    if not os.path.exists(target) or not os.path.isfile(target):
        if cit["kind"] == "line":
            return None, "cited file does not exist: %s (from `%s`)" % (cit["path"], cit["raw"])
        return None, None  # bare and unresolved: prose, not a citation
    row["file_sha256"] = sha256_bytes(read_bytes(target))
    if cit["kind"] == "line":
        lines = read_lines(target)
        n = len(lines)
        if cit["line_start"] > n:
            return None, ("cited span %d-%d is past the end of %s (%d lines)"
                          % (cit["line_start"], cit["line_end"], cit["path"], n))
        a = cit["line_start"]
        b = min(cit["line_end"], n)
        ws, we = window_bounds(a, b, n)
        row["window_start"] = ws
        row["window_end"] = we
        row["window_len"] = we - ws + 1
        row["window_sha256"] = hash_window(lines, ws, we)
        row["file_lines"] = n
    return row, None


def cmd_bind(args):
    if getattr(args, "manifest", None):
        return bind_manifest(args)
    if not args.diagrams_dir:
        die("bind needs a diagrams dir or --manifest")
    diagrams_dir = os.path.abspath(args.diagrams_dir)
    if not os.path.isdir(diagrams_dir):
        die("not a directory: %s" % diagrams_dir)
    if not STAMP_RE.match(args.stamp):
        die("--stamp must be ISO 8601 (e.g. 2026-08-15T09:00:00Z), got %r" % args.stamp)
    # default matches cmd_check's AP-09 fix: cites resolve against the repo root
    # this script runs in, never the diagrams dir or a bound absolute path
    source_root = os.path.abspath(args.source_root) if args.source_root else REPO_ROOT
    if not os.path.isdir(source_root):
        die("--source-root is not a directory: %s" % source_root)

    files = find_diagrams(diagrams_dir)
    if not files:
        die("no diagram .md files under %s" % diagrams_dir)

    diagrams = {}
    errors = []
    for path in files:
        key = rel(path, diagrams_dir)
        parsed = parse_diagram(path)
        for p in parsed["problems"]:
            errors.append("%s: %s" % (key, p))
        cits = []
        for cit in parsed["citations"]:
            row, err = fingerprint_citation(cit, source_root)
            if err:
                errors.append("%s: %s" % (key, err))
            elif row is not None:
                cits.append(row)
            else:
                parsed["ignored"].append(cit["raw"])
        diagrams[key] = {
            "file": key,
            "title": parsed["title"],
            "audience": parsed["audience"],
            "audience_dir_hint": dir_hint(key),
            "citations": cits,
            "ignored_barewords": sorted(set(parsed["ignored"])),
        }

    if errors:
        sys.stderr.write("bind failed — %d error(s), no index written:\n" % len(errors))
        for e in errors:
            sys.stderr.write("  %s\n" % e)
        return 1

    index = {
        "schema": INDEX_SCHEMA,
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "bound_at": args.stamp,
        "diagrams_dir": diagrams_dir,
        "source_root": source_root,
        "window_context_lines": WINDOW,
        "diagrams": diagrams,
    }
    out = os.path.join(diagrams_dir, INDEX_NAME)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, sort_keys=True)
        fh.write("\n")

    n_cit = sum(len(d["citations"]) for d in diagrams.values())
    n_ign = sum(len(d["ignored_barewords"]) for d in diagrams.values())
    print("bound %d diagram(s), %d citation(s), %d bareword(s) ignored as prose"
          % (len(diagrams), n_cit, n_ign))
    print("stamp       %s" % args.stamp)
    print("source root %s" % source_root)
    print("index       %s" % out)
    return 0


# ------------------------------------------------------------------ check ----

def check_citation(row, source_root):
    """Recompute one citation.  Returns a typed result row."""
    out = dict(row)
    target = os.path.normpath(os.path.join(source_root, row["path"]))
    if not os.path.isfile(target):
        out["state"] = "STALE"
        out["reason"] = "cited file is gone"
        return out
    cur_file_sha = sha256_bytes(read_bytes(target))
    out["current_file_sha256"] = cur_file_sha
    if cur_file_sha == row.get("file_sha256"):
        out["state"] = "FRESH"
        out["reason"] = ""
        out["delta_lines"] = 0
        return out

    # the file changed; the window hash adjudicates whether the claim survived
    if row["kind"] != "line" or "window_sha256" not in row:
        out["state"] = "STALE"
        out["reason"] = ("bare citation, file content changed — no line span to "
                         "prove the cited claim survived")
        return out

    lines = read_lines(target)
    table = all_window_hashes(lines, row["window_len"])
    starts = table.get(row["window_sha256"])
    if not starts:
        out["state"] = "STALE"
        out["reason"] = "cited window's content is gone or changed"
        return out
    old = row["window_start"]
    best = min(starts, key=lambda s: (abs(s - old), s))
    delta = best - old
    out["state"] = "MOVED"
    out["delta_lines"] = delta
    out["new_window_start"] = best
    out["new_window_end"] = best + row["window_len"] - 1
    if row["line_start"] is not None:
        shift = best - old
        out["new_line_start"] = row["line_start"] + shift
        out["new_line_end"] = row["line_end"] + shift
    out["reason"] = ("content intact, lines shifted by %+d" % delta if delta
                     else "content intact at the same lines; the file changed elsewhere")
    return out


def load_index(diagrams_dir):
    p = os.path.join(diagrams_dir, INDEX_NAME)
    if not os.path.isfile(p):
        die("no %s in %s — run `bind` first" % (INDEX_NAME, diagrams_dir))
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def load_redlines(diagrams_dir):
    p = os.path.join(diagrams_dir, REDLINES_NAME)
    rows = []
    if not os.path.isfile(p):
        return rows
    with open(p, encoding="utf-8") as fh:
        for i, ln in enumerate(fh, 1):
            ln = ln.strip()
            if not ln:
                continue
            try:
                row = json.loads(ln)
            except ValueError:
                sys.stderr.write("warning: %s line %d is not JSON, skipped\n" % (p, i))
                continue
            if not isinstance(row, dict) or not isinstance(row.get("diagram"), str):
                sys.stderr.write("warning: %s line %d is not a redline row, skipped\n" % (p, i))
                continue
            rows.append(row)
    return rows


def open_redline_counts(diagrams_dir):
    counts = {}
    for r in load_redlines(diagrams_dir):
        if r.get("status") == "open":
            counts[r.get("diagram")] = counts.get(r.get("diagram"), 0) + 1
    return counts


def cmd_check(args):
    if getattr(args, "manifest", None):
        return check_manifest(args)
    if not args.diagrams_dir:
        die("check needs a diagrams dir or --manifest")
    diagrams_dir = os.path.abspath(args.diagrams_dir)
    index = load_index(diagrams_dir)
    bound_source_root = index["source_root"]
    # The bind-time --source-root is kept as provenance only: resolving
    # against it here would silently inherit a decommissioned machine's path
    # (see AP-09) whenever this checkout does not sit at that same absolute
    # location.  The live default is this repo's own root; an explicit
    # --source-root still overrides everything.
    source_root = os.path.abspath(args.source_root) if args.source_root else REPO_ROOT
    reds = open_redline_counts(diagrams_dir)

    rows = []
    for key in sorted(index["diagrams"]):
        d = index["diagrams"][key]
        cits = [check_citation(c, source_root) for c in d["citations"]]
        states = [c["state"] for c in cits]
        if "STALE" in states:
            state = "STALE"
        elif "MOVED" in states:
            state = "MOVED"
        else:
            state = "FRESH"
        hint = d.get("audience_dir_hint")
        seal_ok = True
        seal_note = ""
        if hint and d.get("audience") and d["audience"] != hint:
            seal_ok = hint != "ROOM-SAFE"  # INTERNAL sitting in room/ is the leak
            seal_note = "audience %s filed under a %s directory" % (d["audience"], hint)
        rows.append({
            "file": key,
            "title": d.get("title"),
            "audience": d.get("audience"),
            "state": state,
            "citations_total": len(cits),
            "citations_fresh": states.count("FRESH"),
            "citations_moved": states.count("MOVED"),
            "citations_stale": states.count("STALE"),
            "open_redlines": reds.get(key, 0),
            "seal_ok": seal_ok,
            "seal_note": seal_note,
            "detail": [c for c in cits if c["state"] != "FRESH"],
        })

    any_stale = any(r["state"] == "STALE" for r in rows)
    any_moved = any(r["state"] == "MOVED" for r in rows)
    code = 1 if any_stale else (2 if any_moved else 0)

    orphan = sorted(k for k in reds if k not in index["diagrams"])
    summary = {
        "diagrams": len(rows),
        "fresh": sum(1 for r in rows if r["state"] == "FRESH"),
        "moved": sum(1 for r in rows if r["state"] == "MOVED"),
        "stale": sum(1 for r in rows if r["state"] == "STALE"),
        "open_redlines": sum(r["open_redlines"] for r in rows) + sum(reds[k] for k in orphan),
        "seal_violations": sum(1 for r in rows if not r["seal_ok"]),
        "exit_code": code,
    }

    if args.json:
        print(json.dumps({
            "schema": CHECK_SCHEMA,
            "tool": TOOL,
            "tool_version": TOOL_VERSION,
            "bound_at": index["bound_at"],
            "diagrams_dir": diagrams_dir,
            "source_root": source_root,
            "bound_source_root": bound_source_root,
            "rows": rows,
            "orphan_redline_diagrams": orphan,
            "summary": summary,
        }, indent=2, sort_keys=True))
        return code

    w = max([len(r["file"]) for r in rows] + [7])
    root_note = source_root
    if bound_source_root != source_root:
        root_note = "%s  (bound: %s)" % (source_root, bound_source_root)
    print("atlas check — bound %s — source root %s" % (index["bound_at"], root_note))
    print("%-*s  %-9s  %-5s  %-13s  %-8s  %s"
          % (w, "DIAGRAM", "AUDIENCE", "STATE", "CITES f/m/s", "REDLINES", "NOTE"))
    print("-" * (w + 60))
    for r in rows:
        note = ""
        if r["detail"]:
            d0 = r["detail"][0]
            note = "%s: %s" % (d0["raw"], d0["reason"])
            if len(r["detail"]) > 1:
                note += "  (+%d more)" % (len(r["detail"]) - 1)
        print("%-*s  %-9s  %-5s  %-13s  %-8s  %s"
              % (w, r["file"], r["audience"] or "?", r["state"],
                 "%d/%d/%d" % (r["citations_fresh"], r["citations_moved"], r["citations_stale"]),
                 r["open_redlines"], note))
        if not r["seal_ok"]:
            print("%-*s  SEAL: %s" % (w, "", r["seal_note"]))
    print("-" * (w + 60))
    print("%d diagram(s): %d FRESH, %d MOVED, %d STALE — %d open redline(s) — exit %d"
          % (summary["diagrams"], summary["fresh"], summary["moved"],
             summary["stale"], summary["open_redlines"], code))
    if orphan:
        print("open redlines against unknown diagrams: %s" % ", ".join(orphan))
    return code


# ---------------------------------------------------------------- redline ----

def compact_stamp(stamp):
    return re.sub(r"[^0-9A-Za-z]", "", stamp)


def cmd_redline(args):
    diagrams_dir = os.path.abspath(args.diagrams_dir)
    if not os.path.isdir(diagrams_dir):
        die("not a directory: %s" % diagrams_dir)

    index = None
    ipath = os.path.join(diagrams_dir, INDEX_NAME)
    if os.path.isfile(ipath):
        with open(ipath, encoding="utf-8") as fh:
            index = json.load(fh)

    stamp = args.stamp
    stamp_source = "argument"
    if not stamp:
        # no clock read: fall back to the bind stamp, so the row is honestly
        # dated "against this bind" rather than against an unrecorded now
        if index is None:
            die("--stamp is required when no %s exists to inherit a stamp from" % INDEX_NAME)
        stamp = index["bound_at"]
        stamp_source = "inherited from bind"
    if not STAMP_RE.match(stamp):
        die("--stamp must be ISO 8601, got %r" % stamp)

    diagram = args.diagram.replace(os.sep, "/")
    if index is not None and diagram not in index["diagrams"]:
        cand = [k for k in index["diagrams"] if k.endswith("/" + diagram) or k == diagram]
        if len(cand) == 1:
            diagram = cand[0]
        else:
            die("diagram %r is not in the index (known: %s)"
                % (args.diagram, ", ".join(sorted(index["diagrams"]))))

    text = args.text.strip()
    if not text:
        die("--text must not be empty")

    cs = compact_stamp(stamp)
    existing = load_redlines(diagrams_dir)
    n = sum(1 for r in existing if str(r.get("id", "")).startswith("RL-%s-" % cs)) + 1
    rid = "RL-%s-%02d" % (cs, n)

    row = {
        "schema": REDLINE_SCHEMA,
        "id": rid,
        "diagram": diagram,
        "author": args.author,
        "text": text,
        "stamp": stamp,
        "status": "open",
    }
    path = os.path.join(diagrams_dir, REDLINES_NAME)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    if args.json:
        print(json.dumps(row, indent=2, sort_keys=True))
    else:
        print("redline %s banked against %s (stamp %s, %s)" % (rid, diagram, stamp, stamp_source))
        print("  %s: %s" % (args.author, text))
        print("  -> %s" % path)
    return 0


def cmd_redlines(args):
    diagrams_dir = os.path.abspath(args.diagrams_dir)
    rows = load_redlines(diagrams_dir)
    if args.open_only:
        rows = [r for r in rows if r.get("status") == "open"]
    rows.sort(key=lambda r: (str(r.get("diagram")), str(r.get("id"))))
    if args.json:
        print(json.dumps({
            "schema": REDLINES_REPORT_SCHEMA,
            "tool": TOOL,
            "tool_version": TOOL_VERSION,
            "diagrams_dir": diagrams_dir,
            "rows": rows,
            "summary": {"rows": len(rows),
                        "open": sum(1 for r in rows if r.get("status") == "open")},
        }, indent=2, sort_keys=True))
        return 0
    if not rows:
        print("no redlines in %s" % os.path.join(diagrams_dir, REDLINES_NAME))
        return 0
    cur = None
    for r in rows:
        if r.get("diagram") != cur:
            cur = r.get("diagram")
            print("\n%s" % cur)
        print("  %s  [%s]  %s" % (r.get("id"), r.get("status"), r.get("author")))
        print("      %s" % r.get("text"))
        print("      stamp %s" % r.get("stamp"))
    print("\n%d row(s), %d open" % (len(rows), sum(1 for r in rows if r.get("status") == "open")))
    return 0


# ------------------------------------------------------------------- main ----

def die(msg):
    sys.stderr.write("error: %s\n" % msg)
    raise SystemExit(1)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="atlas_bind", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    b = sub.add_parser("bind", help="fingerprint every diagram's citations")
    b.add_argument("diagrams_dir", nargs="?", default=None)
    b.add_argument("--manifest", default=None,
                   help="bind the FROZEN SURFACE LIST in this manifest file instead of a "
                        "diagrams dir (whole-doc scan; index lands beside the manifest)")
    b.add_argument("--stamp", required=True,
                   help="ISO 8601 bind timestamp; required, never read from the clock")
    b.add_argument("--source-root", default=None,
                   help="root the citations resolve against (default: the diagrams dir)")
    b.set_defaults(func=cmd_bind)

    c = sub.add_parser("check", help="recompute and report FRESH / MOVED / STALE "
                                     "(+ UNGROUNDED in --manifest mode)")
    c.add_argument("diagrams_dir", nargs="?", default=None)
    c.add_argument("--manifest", default=None,
                   help="check the bound surface manifest instead of a diagrams dir")
    c.add_argument("--source-root", default=None,
                   help="override the source root recorded in the index")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_check)

    r = sub.add_parser("redline", help="bank a correction as a typed row")
    r.add_argument("diagrams_dir")
    r.add_argument("--diagram", required=True)
    r.add_argument("--author", required=True)
    r.add_argument("--text", required=True)
    r.add_argument("--stamp", default=None,
                   help="ISO 8601; defaults to the bind stamp in the index")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_redline)

    rr = sub.add_parser("redlines", help="list banked redlines")
    rr.add_argument("diagrams_dir")
    rr.add_argument("--all", dest="open_only", action="store_false", default=True,
                    help="include consumed rows (default: open only)")
    rr.add_argument("--json", action="store_true")
    rr.set_defaults(func=cmd_redlines)

    args = ap.parse_args(argv)
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
