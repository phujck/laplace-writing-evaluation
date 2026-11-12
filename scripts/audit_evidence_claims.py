#!/usr/bin/env python3
"""audit_evidence_claims.py — catch claims-about-files that the record doesn't satisfy.

Bank-time auditor for the class of gap the judge caught by hand on 2026-08-15:
evidence/call_2026-08-14_andrew-jack-gerard/extraction.md line 1 asserts "raw transcript
beside this file" while the directory holds no transcript. This walks evidence/**/*.md
and flags claims about files that do not exist. stdlib only.

WHAT COUNTS AS A CLAIM (kept narrow on purpose — false positives cost more than a missed
edge case; both claim classes are heuristic, not a parser)
----------------------------------------------------------------------------------------
1. SIBLING ASSERTIONS. A line containing one of a small set of proximity phrases
   ("beside this file", "alongside this file", "in this directory", "next to this file",
   "in the same directory") *and*, on that same line, a word that names or implies a file
   (transcript/recording/screenshot/stdout/stderr/output/dump/audio/video, or a format
   name like json/csv/txt/pdf/log/yaml/png/jpg, or a bare filename ending in a known
   extension). Matching is done per physical line, not per logical sentence — a phrase and
   its noun split across a hard-wrapped line would be missed; every case found in this
   corpus keeps both on one line, so the simpler rule was kept.
   Resolution is always against the claiming file's OWN directory (that is what "beside
   this file" / "in this directory" asserts):
     - if the line also names an explicit filename (backticked or bare, known extension),
       that exact name is checked for in the directory;
     - otherwise the claim is generic ("a transcript exists here") and is checked by
       keyword: does any other file in the directory match the claimed word (extension
       equality for format words, substring-of-filename for noun words)?

2. EXPLICIT RELATIVE PATH REFERENCES. Three sub-forms, all requiring a recognized
   extension (md/json/jsonl/txt/csv/yaml/yml/png/jpg/jpeg/pdf/log/mp3/mp4/wav/py/sh/ts/js)
   so a bare directory mention like "evidence/" never counts as a claim on its own.
   Between them they cover every relative path shape: with the evidence/ · ./ · ../
   prefixes (a), with any other directory prefix (c), and with no prefix at all (b).
     a. repo-relative paths spelled with an explicit prefix — `evidence/...`, `./...`,
        `../...` (backticked or bare). `evidence/...` resolves from the repo root;
        `./...` and `../...` resolve from the claiming file's own directory.
     b. bare filenames — a token with a known extension and no `/` in it at all
        (e.g. `ablation_result.json`). Where the prose puts such a name is decided by
        DIRECTORY ATTRIBUTION (below); if that yields nothing the name is read as a
        same-directory claim. Whatever directory is chosen, the name is also looked up
        in the claiming file's own directory and then repo-wide by basename before
        anything is called a gap — evidence prose routinely names a script or a shared
        artifact that lives elsewhere in the repo (`wake.py`,
        `wake_vs_descent_decomposition.json`) without a path, and those are not gaps.
        This was tuned in: v1 checked same-directory only and it flooded on every such
        reference (see PROVE run below); the repo-wide fallback is the fix, and it is one
        of the script's two deliberate loosenings (the other is its n-segment counterpart
        in (c)) — it can produce a false negative if a
        claimed filename happens to collide with an unrelated file elsewhere in the repo,
        which is judged the safer failure mode for a bank-time gate that must not cry wolf.
     c. relative paths with ANY other directory prefix — `paper_falqon/manuscript/main.pdf`,
        `inputs/source.pdf`, `judge_rounds/harnessed_round1.json`. Added in v4 against the
        counterexample that refuted v3: evidence/FIRST_CHAIR_2026-07-17_seam5.md:9 claims to
        have opened `paper_falqon/manuscript/main.pdf`, which is not in the tree, and (a)+(b)
        were structurally blind to it — (a) only knows three prefixes and (b) only knows
        tokens with no "/" at all. Three prefix-specific guards keep this sub-form honest:
          - BACKTICKED ONLY (the same reasoning that gates CODE_EXTENSIONS and directory
            tokens). Every genuine multi-segment reference observed in this corpus is
            backticked, and the unbackticked population is actively misleading — see the
            heuristics note below.
          - CONCRETE FILE ONLY: the token must end in a recognized extension, so a bare
            directory mention (`manuscript/rounds/`) never becomes a claim.
          - REPO-WIDE PATH-SUFFIX FALLBACK, resolution order own-directory then repo root,
            then the fallback. This is class 2b's repo-wide basename fallback re-validated
            for n segments rather than reused as-is, which matters in both directions:
            reused as-is it would be too LOOSE and would suppress the very row this
            sub-form exists to catch (other `main.pdf` files do exist in the tree), while
            dropping it entirely would be too STRICT — see the heuristics note.

DIRECTORY ATTRIBUTION (class 2b — where the prose says a bare filename lives)
----------------------------------------------------------------------------------------
A bare filename in evidence prose is usually preceded by the directory that holds it
("Screenshots ... are in `scratchpad/census/` (`desk-8778.png`, `conceptric-8778.png`,
...)"). v2 ignored that and resolved every bare name against the claiming file's own
directory, so the reported "missing" path was one the document never asserted — the
defect that refuted v2 (11 of 12 rows on the real tree). Attribution now runs in three
steps, first hit wins:
  i.   a backticked directory token (`something/`, `./something/`, ending in "/" and not
       part of a longer path-with-file) earlier on the SAME line;
  ii.  the last such token earlier in the same PARAGRAPH (a run of non-blank lines) —
       the list above is hard-wrapped across four lines and only the first carries the
       directory;
  iii. a document-level basename→directory map built from (i)/(ii): a bare name declared
       once with a directory is read the same way when the same document re-mentions it
       later without one (the `pipeline-8778.png` table cells at lines 76/225/322).
Attribution only changes WHERE a claim is read as pointing; the own-directory and
repo-wide existence checks still run, so it cannot manufacture a gap that v2 did not
already report.

SEVERITY: SCRATCH REFERENCES ARE A DIFFERENT CLASS
----------------------------------------------------------------------------------------
A claim that resolves under a working/scratch directory (SCRATCH_DIR_ROOTS: scratchpad/,
artifacts/, tmp/) is reported as claim_class "scratch_reference" with severity "note",
not as a committed-evidence gap. Those directories are expected-ephemeral by this repo's
own convention — .gitignore's "local-only renders + scratch" block, and OPEN_STACK.md's
N50 row marking a `scratchpad/` citation "(EPHEMERAL, LOST ...; do not re-cite)". A
missing scratch capture is a stale citation; a missing transcript beside a committed
extraction is a record that does not hold. Exit status counts gaps only unless --strict
is passed, which counts notes too.

SEVERITY: REGENERABLE — A THIRD CLASS, ADDED 2026-08-15
----------------------------------------------------------------------------------------
Granted on the ruling "absent but regenerable might be a worthwhile tag": a permanently-red
row that needs no action rots the alarm. A class-2 (explicit-path) row whose missing path
is deliberately ignored by git — not lost, not a stale scratch citation, but excluded from
the tracked tree ON PURPOSE — is reported with severity "regenerable" instead of "gap".
The rationale in one sentence: it is a reading claim that cannot be re-opened from the
record as it stands, where the cause is regenerability rather than loss — re-render to
re-open. It still means the artefact is not there to open right now, so it still prints
(table and --json) and still counts under --strict; it just does not fail the default,
un-strict run the way an unexplained gap does.

Discriminator: walk from the missing path's own directory upward to the repo root,
collecting each ancestor's .gitignore file (nearest first). The first such file whose
patterns match the missing path decides the row; a match makes it "regenerable" unless
the negation fallback below applies, in which case it stays "gap".

GITIGNORE-SUBSET MATCHING (stdlib only, deliberately partial — see GitignoreMatch below)
----------------------------------------------------------------------------------------
This is a DOCUMENTED SUBSET of gitignore pattern syntax, not a parser: real gitignore
supports `**`, `?`, character classes, and order-dependent negation across an arbitrary
number of files. None of that is implemented. What each non-blank, non-comment line in a
collected .gitignore IS read as (checked against the missing path relative to that
.gitignore's OWN directory, `rel`, and its basename, `base`):
  - exact basename lines, no "/" at all (e.g. `main.pdf`) — matches iff `base == pattern`,
    regardless of how deep under the .gitignore's directory the missing path sits (the
    real-gitignore behavior for a slash-free pattern).
  - exact relative-path lines, containing a "/" and not ending in one (e.g.
    `manuscript/main.pdf`) — matches iff `rel == pattern`. A single leading "/" (git's
    root-anchor marker) is stripped before comparison so `/main.pdf` and `main.pdf` in
    this bucket behave alike; anything past that first slash is read literally.
  - trailing-"/" directory lines (e.g. `build/`) — matches iff `rel == pattern` (slash
    stripped) or `rel` starts with `pattern` (i.e. anything under that directory).
  - `*.ext` suffix globs (e.g. `*.log`) — matches iff `base` ends with `.ext`. No other
    glob metacharacter is interpreted; a pattern with `?`, `[`, or an embedded `*` that
    isn't this exact `*.ext` shape is not matched at all (silently skipped, not an error).
NO NEGATION SUPPORT: if the .gitignore file whose pattern matched ALSO contains a `!`-line
whose un-negated pattern matches the same missing path under this same subset, the match is
judged UNSAFE — a real negation could re-include the path, and this script cannot resolve
gitignore's order-dependent precedence to know whether it does — so severity falls back to
"gap" and the row detail says so explicitly. This is deliberately narrow: a negation line
elsewhere in the file that does NOT match this path (e.g. `!main.log` beside a `main.pdf`
rule) does not trigger the fallback — only a negation that collides with the specific match
does. Only the FIRST matching .gitignore file (nearest to the missing path) is consulted;
files further up the tree are not combined with it even if they also have a pattern.

CLASS-2C HEURISTICS (the two tunings above, each measured on the real tree)
----------------------------------------------------------------------------------------
Both were fixed against the v4 tuning run over evidence/ (2026-08-15), which produced 17
unresolved backticked prefixed paths before either rule:
  - PATH-SUFFIX FALLBACK (the one deliberate loosening, and the only tuning this repair
    needed). 15 of those 17 rows were the same legitimate pattern: evidence prose cites a
    path relative to a PROJECT root that is neither the claiming file's directory nor the
    repo root — `judge_rounds/harnessed_round1.json` and `manuscript/feedback/
    reader_ledger_r1.json` mean paper_falqon/..., `inputs/paper_b_2301.12069_enz-feedback
    .pdf` in stage_3/ means its packet's sibling inputs/ directory one level up,
    `writing_organ/breath.py` means src/laplace/..., `publication/release_manifest.json`
    means a synthetics paper's own root. All 15 are real files at a real path; only the
    implied root is unstated. Asking "does any file in the repo end with this whole
    multi-segment tail" clears all 15 and leaves 2 — the FIRST_CHAIR seam5/seam6
    `paper_falqon/manuscript/main.pdf` rows, i.e. 17 -> 2 with a 0/2 false-positive rate.
    Note this must be the PATH suffix, not class 2b's basename: `main.pdf` exists under
    paper_operatorial_loss/, paper_eigen/, paper_self_theory/ and more, so a basename-only
    fallback would have suppressed the refuting counterexample itself. The same false
    negative as 2b remains possible (a claimed path that coincidentally tails a real file
    elsewhere), and is the same judged-safer failure mode for a gate that must not cry wolf.
  - BACKTICKED ONLY. The unbackticked population is not merely noisier, it is wrong: all
    11 of its post-fallback survivors are one artifact, a directory name containing a SPACE
    (`synthetics papers/feedback-twinning-fields/...`). This regex cannot spell a space, so
    it matches the tail `papers/feedback-twinning-fields/...` and reports a path the
    document never wrote — 11/11 spurious, and every one of those files exists. The opening
    backtick sits before "synthetics", so requiring backticks on BOTH ends of the match
    discards exactly this class. Cost of the guard: an unbackticked prefixed path is not
    checked at all (see NOT attempted).

   Skipped unconditionally: URLs (`http://`/`https://` spans); anything glob-like or
   illustrative (the matched text contains `<`, `>`, `*`, or `...`); text inside a fenced
   code block whose fence is marked as an example (info-string contains "example", or the
   nearest preceding non-blank line does — e.g. "For example:" / "**Example**"). Fences
   not marked as an example ARE scanned — several evidence files embed a real derivation
   script that references a real path, and that path claim is exactly the kind of thing
   worth checking.

NOT attempted: sentence parsing, claims spanning multiple lines, path claims using
extensions outside the list above, or anything inside an un-marked code fence being
treated specially (it isn't — it's scanned like prose, which is the point). Also not
attempted, all class-2c edges: unbackticked prefixed paths (the backtick guard above),
paths whose directory names contain spaces (unspellable by these regexes — the very case
that guard discards), and absolute paths (`/tmp/...`, `/home/...`), which the leading
lookbehind refuses rather than mistaking their tails for relative paths. The directory-
prefix gap itself is NO LONGER out of scope — class 2c covers it as of v4; what remains
unchecked is only those three spellings of it.

A caught class-2c row says the cited path is not in the tree. It does not, by itself,
distinguish WHY: both v4 rows cite `paper_falqon/manuscript/main.pdf`, which
paper_falqon/manuscript/.gitignore names as a "regenerable working PDF" while the named
release artefacts stay tracked. Deliberately absent-by-design is still absent — a
first-chair reading claim whose artefact cannot be re-opened from the record is exactly
what this gate is for, which is why v4 left both rows as "gap" rather than suppressing
them (suppressing on ignore rules would have swallowed the row this sub-form exists to
catch) — but the grader reading the row should know the file was ignored, not lost. v5
(this version) resolves that by consulting the actual .gitignore files (not just the
claiming line's own prose, which is all GITIGNORED_RE reads) and reporting such rows at
severity "regenerable" instead of "gap" — see SEVERITY: REGENERABLE and
GITIGNORE-SUBSET MATCHING above. Nothing is suppressed; the row still prints and still
counts under --strict.

Exit code: 0 with zero gaps, 1 with one or more gaps (consumable by a close checklist
later — this script does not wire itself into one). Scratch-reference notes and
regenerable rows do not affect the exit status unless --strict is passed.

PROVE RUNS (the tunings above cite these; each named heuristic was added against a row
one of them printed)
----------------------------------------------------------------------------------------
- v1/v2 tuning runs over the repo's own evidence/ tree, 2026-08-15: the .jsonl/.json
  alternation-order bug, the hyphen-boundary split, `pdf.js`, the T13/T14 table labels,
  the negated/gitignored `spans.jsonl` sentence, the `*_regraded.json` glob and the
  ellipsis-truncated header were each a printed row before they were a rule here.
- v3 (this version), same tree: 1 gap + 11 scratch notes, exit 1. The gap is the
  2026-08-14 transcript case this script was built for. All 11 notes are the one
  scratchpad/census/ capture set, now reported at the path the document actually
  asserts. Same 12 (file, line) rows as v2 — attribution changed where they point and
  how they are graded, and added or dropped nothing.
- v3 also printed `before/after/pipeline-8778.png` on its first run (prose alternation
  read as a directory), which is why directory tokens must be backticked.
- v4 (this version), same tree: 3 gaps + 11 scratch notes, exit 1. v3's single gap (the
  2026-08-14 transcript) is unchanged and still caught; the 11 notes are unchanged; class
  2c adds exactly the 2 `paper_falqon/manuscript/main.pdf` rows (FIRST_CHAIR seam5:9,
  seam6:3). Both new rows were hand-checked against the tree: real gaps, 0/2 false
  positives. The two class-2c heuristics were measured before being written, on the 17
  candidate rows the un-guarded sub-form produced — see CLASS-2C HEURISTICS above.
- v5 (this version), same tree: 1 gap + 2 regenerable + 11 scratch notes, exit 1. The two
  `paper_falqon/manuscript/main.pdf` rows (FIRST_CHAIR seam5:9, seam6:3) move from "gap"
  to "regenerable" — paper_falqon/manuscript/.gitignore's `main.pdf` line matches both,
  and that file's one negation line (`!main.log`) does not match `main.pdf` so the
  negation fallback does not fire. The 2026-08-14 transcript gap is unchanged (no
  .gitignore anywhere from evidence/call_2026-08-14_andrew-jack-gerard/ up to the repo
  root names a transcript file), so exit stays 1 — a true gap remains. The 11 scratch
  notes are unchanged. --strict now also elevates the 2 regenerable rows (exit 1, as it
  already did via the notes).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Shared vocab
# ---------------------------------------------------------------------------

# Extensions a "file claim" is allowed to end in. Deliberately includes a few code
# extensions (py/sh/ts/js) because evidence prose does reference scripts by bare name;
# the repo-wide fallback (see module docstring, class 2b) is what keeps that safe.
# ORDER MATTERS: regex alternation takes the first branch that matches, not the longest,
# so "json" must not precede "jsonl" (else ".jsonl" matches only ".json" and strands the
# "l" — a real bug caught in the PROVE run: it truncated a genuine
# `evidence/LOOP_TRAJECTORY_2026-07-16.jsonl` reference into a false-positive claim about
# a nonexistent `.json` file). Same reasoning keeps "js" last, after "json"/"jsonl".
EXTENSIONS = (
    "md|jsonl|json|txt|csv|yaml|yml|png|jpe?g|pdf|log|mp3|mp4|wav|py|sh|ts|js"
)

# Extensions treated as ambiguous prose words unless backticked (class 2b only — see
# check_explicit_paths). Bare, unbackticked mentions of these collide with real English
# (a tool/library name like "pdf.js", not a claim about a file in this repo) far more
# than they catch genuine references — every genuine same-repo script mention observed
# in this corpus was backticked. Tuned in after the PROVE run flagged "pdf.js" (the
# Mozilla PDF reader library, named in prose, not a file in this repo) as a gap twice.
CODE_EXTENSIONS = {"py", "sh", "ts", "js"}

# Sibling-assertion proximity phrases (class 1). The task names the first three
# verbatim ("phrases like ..."); "next to this file" and "in the same directory" are
# obvious synonyms added so a trivial rewording doesn't slip the net.
SIBLING_PHRASES = [
    "beside this file",
    "alongside this file",
    "in this directory",
    "next to this file",
    "in the same directory",
]
SIBLING_RE = re.compile(
    "(" + "|".join(re.escape(p) for p in SIBLING_PHRASES) + ")", re.IGNORECASE
)

# Words that name or imply a file, for the generic (no-explicit-filename) sibling case.
# Split into "format words" (checked by extension-in-directory) and "noun words"
# (checked by substring-in-filename) — see _dir_has_match_for_keyword.
FORMAT_WORDS = {
    "json", "csv", "txt", "pdf", "log", "yaml", "yml",
    "mp3", "mp4", "wav", "png", "jpg", "jpeg", "md",
}
NOUN_WORDS = {
    "transcript", "recording", "screenshot", "screenshots", "stdout", "stderr",
    "output", "dump", "audio", "video",
}
FILE_NOUN_RE = re.compile(
    r"\b(" + "|".join(sorted(FORMAT_WORDS | NOUN_WORDS)) + r")\b", re.IGNORECASE
)

# An explicit filename token appearing directly in a line: optional backticks, a bare
# name/path fragment, ending in a recognized extension.
FILENAME_TOKEN_RE = re.compile(
    r"`?([A-Za-z0-9_\-./]+\.(?:" + EXTENSIONS + r"))`?"
)

# Class 2a: repo-relative paths with the evidence/ · ./ · ../ prefixes, ending in a known
# extension. Negative lookbehind keeps this from matching mid-path (e.g. the "evidence/"
# inside "some/other/evidence/x.json" is not what we mean here — the whole path is class
# 2c's now, and the lookbehind also stops a match starting mid-word). The prefix set stays
# narrow because these three resolve by special rules (repo root; claiming directory); any
# other prefix is class 2c, which resolves by search rather than by rule.
REPO_RELATIVE_RE = re.compile(
    r"(?<![\w/.\-])((?:evidence/|\.\./|\./)[A-Za-z0-9_\-./]*\.(?:" + EXTENSIONS + r"))"
)

# Class 2c: a relative path with ANY other directory prefix — `paper_falqon/manuscript/
# main.pdf`, `inputs/source.pdf`, `judge_rounds/harnessed_round1.json`. The lookaheads hand
# the evidence/ · ./ · ../ prefixes back to class 2a (which resolves them differently and is
# already tuned); everything else lands here. At least one "/" is required, so class 2b keeps
# the no-slash tokens. The leading lookbehind excludes "/" and "." so this cannot start
# mid-path (the "manuscript/main.pdf" inside "paper_falqon/manuscript/main.pdf" is one match,
# not two) and cannot pick up the tail of an absolute path.
PREFIXED_RELATIVE_RE = re.compile(
    r"(?<![\w/.\-])(?!evidence/)(?!\.{1,2}/)"
    r"([A-Za-z0-9_\-.]+(?:/[A-Za-z0-9_\-.]+)+\.(?:" + EXTENSIONS + r"))"
)

# Class 2b: bare same-directory filenames — no "/" anywhere in the token. Lookbehind/
# lookahead exclude "-" and "." (not just \w and "/") so this cannot start or end
# mid-token inside a larger hyphenated path already covered by REPO_RELATIVE_RE —
# e.g. must not split `ATLAS_PHASE3_2026-08-01_stop-condition.md` into a bogus
# `08-01_stop-condition.md` match at the hyphen boundary (caught in the PROVE run below).
BARE_FILENAME_RE = re.compile(
    r"(?<![\w/.\-])([A-Za-z0-9_\-]+\.(?:" + EXTENSIONS + r"))(?![\w/\-])"
)

# Directory tokens for class-2b attribution: a run of path segments ending in "/", with
# nothing path-like after the final slash (so the "evidence/" inside "evidence/x.json" is
# not read as a standalone directory mention — that whole path is class 2a's job).
DIR_TOKEN_RE = re.compile(
    r"(?<![\w/.\-])((?:\.{1,2}/)?(?:[A-Za-z0-9_\-.]+/)+)(?![A-Za-z0-9_\-.])"
)

# Directories this repo treats as working/scratch space: expected-ephemeral, never part
# of the committed record. Grounded in .gitignore's "local-only renders + scratch" block
# (artifacts/) and OPEN_STACK.md's N50 row, which marks a `scratchpad/` citation
# "(EPHEMERAL, LOST — friction 400005; do not re-cite)". A claim resolving under one of
# these is a stale citation, not a hole in the record — see the SEVERITY note above.
SCRATCH_DIR_ROOTS = ("scratchpad", "artifacts", "tmp")

URL_RE = re.compile(r"https?://\S+")

FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")

# Table rows ("| cell | cell |") that name a bare (non-backticked) filename as a label —
# tuned in after the PROVE run flagged "T13 agreement.md" / "T14 agreement.md" in a
# results table (evidence/DESCENT_COLLISION_2026-07-29_the-oracle-gate/README.md): a
# carrier nickname, not a same-directory file claim. Backticked cells in the same tables
# (e.g. `_REFINEMENTS.md`) are real references and are unaffected by this rule.
TABLE_ROW_RE = re.compile(r"^\s*\|")

# Negation cues: a match sitting just after one of these is a claim that the file does
# NOT exist, which this script has nothing to say about (it only checks claims of
# existence). Tuned in after the PROVE run flagged
# "no `blobs/` or `spans.jsonl` exists on disk" (evidence/SEV_2026-08-13_profile-perimeter/
# README.md) — the sentence's own point was the absence.
NEGATION_RE = re.compile(
    r"\b(no|not|never|absent|missing|doesn'?t|does\s+not|isn'?t|aren'?t|cannot\s+access)\b",
    re.IGNORECASE,
)
NEGATION_WINDOW = 50

# A file explicitly called out as gitignored is, by definition, expected to be absent
# from the tracked tree — not a claims/record mismatch. Tuned in alongside the negation
# rule (same SEV README paragraph names `blobs/` and `spans.jsonl` as gitignored).
GITIGNORED_RE = re.compile(r"gitignored", re.IGNORECASE)

# Adjacent characters that mark a match as illustrative/glob rather than a real
# reference, even when the match text itself is clean. Tuned in after the PROVE run:
# `*_regraded.json` (glob, asterisk sits just outside the captured filename) and
# `GERARD_PSYCH_PROFILE_…v1.md` (a table header using the unicode ellipsis "…" as a
# truncation marker, not the "..." literal already covered by looks_illustrative).
ADJACENT_ILLUSTRATIVE_CHARS = set("<>*…")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Gap:
    file: str          # repo-relative path of the .md file making the claim
    line: int           # 1-based line number of the claim
    claim_class: str    # "sibling_assertion" | "explicit_path" | "scratch_reference"
    excerpt: str         # the claiming line, trimmed
    missing: str          # the path (or descriptive pattern) that does not exist
    severity: str = "gap"  # "gap" = committed record doesn't hold | "note" = scratch ref
                            # | "regenerable" = class-2 gap whose path is gitignored on
                            #   purpose — see module docstring, SEVERITY: REGENERABLE


def is_scratch_path(rel_path: str) -> bool:
    """True if a repo-relative (or absolute-tmp) path sits under a working/scratch root."""
    p = rel_path.replace("\\", "/").lstrip("./")
    if rel_path.startswith("/tmp/") or rel_path.startswith("/var/tmp/"):
        return True
    head = p.split("/", 1)[0]
    return head in SCRATCH_DIR_ROOTS and "/" in p


# ---------------------------------------------------------------------------
# .gitignore subset matching (severity: regenerable) — see module docstring,
# GITIGNORE-SUBSET MATCHING, for the full documented subset and its limits.
# ---------------------------------------------------------------------------

def _gitignore_line_matches(pattern: str, rel: str, base: str) -> bool:
    """One pattern line (already stripped of comments/blanks/the leading `!` of a
    negation) against a missing path expressed two ways relative to the .gitignore's own
    directory: `rel` (full relative path) and `base` (basename only). Implements exactly
    the four forms documented in the module docstring; anything else (an embedded `*`
    that isn't a bare `*.ext` suffix, `?`, `[...]`, `**`) matches nothing."""
    if pattern.endswith("/"):
        stem = pattern.rstrip("/")
        return rel == stem or rel.startswith(stem + "/")
    if pattern.startswith("*.") and pattern.count("*") == 1 and "/" not in pattern:
        return base.endswith(pattern[1:])
    if "/" in pattern:
        stem = pattern[1:] if pattern.startswith("/") else pattern
        return rel == stem
    return base == pattern


def _find_gitignore_files(start_dir: Path, repo_root: Path) -> list:
    """.gitignore files from `start_dir` up through `repo_root` inclusive, nearest first.
    Empty if `start_dir` is not `repo_root` or a descendant of it."""
    try:
        start_dir.relative_to(repo_root)
    except ValueError:
        return []
    files = []
    d = start_dir
    while True:
        gi = d / ".gitignore"
        if gi.is_file():
            files.append(gi)
        if d == repo_root:
            break
        d = d.parent
    return files


def gitignore_status(missing_path: Path, repo_root: Path):
    """Is `missing_path` (need not exist) matched by a .gitignore between its own
    directory and the repo root? Returns a (status, pattern, gitignore_relpath) triple:
      - ("regenerable", pattern, gi_rel) — the nearest matching .gitignore's rule, safe
        (no colliding negation).
      - ("unsafe_negation", pattern, gi_rel) — matched, but the same file also has a `!`
        line matching this same path; this script cannot resolve the resulting
        precedence, so the caller must keep severity "gap".
      - (None, None, None) — no .gitignore between there and the repo root matches.
    Only the first (nearest) matching file is consulted — see module docstring."""
    for gi_file in _find_gitignore_files(missing_path.parent, repo_root):
        gi_dir = gi_file.parent
        try:
            rel = str(missing_path.relative_to(gi_dir)).replace("\\", "/")
        except ValueError:
            continue
        base = missing_path.name
        try:
            raw_lines = gi_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        positives, negations = [], []
        for raw in raw_lines:
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            (negations if s.startswith("!") else positives).append(
                s[1:].strip() if s.startswith("!") else s
            )
        matched = next((p for p in positives if _gitignore_line_matches(p, rel, base)), None)
        if matched is None:
            continue
        gi_rel = str(gi_file.relative_to(repo_root))
        if any(_gitignore_line_matches(n, rel, base) for n in negations):
            return ("unsafe_negation", matched, gi_rel)
        return ("regenerable", matched, gi_rel)
    return (None, None, None)


def regenerable_severity(base_missing: str, resolved_target: Path, repo_root: Path):
    """Given a class-2 gap's base "missing" detail text and the resolved absolute path it
    refers to, decide whether it upgrades to "regenerable". Returns (severity, missing) —
    unchanged ("gap", base_missing) if no .gitignore matches; ("regenerable", annotated)
    if one does safely; ("gap", annotated) if the match is unsafe (colliding negation)."""
    status, pattern, gi_rel = gitignore_status(resolved_target, repo_root)
    if status == "regenerable":
        return "regenerable", f"{base_missing} [gitignored by `{pattern}` in {gi_rel}]"
    if status == "unsafe_negation":
        return (
            "gap",
            f"{base_missing} [gitignore {gi_rel} matches `{pattern}` but also negates it — "
            "cannot safely resolve under this script's subset; kept as gap]",
        )
    return "gap", base_missing


# ---------------------------------------------------------------------------
# Repo-wide basename index (class 2b fallback) / path-suffix index (class 2c fallback)
# ---------------------------------------------------------------------------

def build_basename_index(root: Path) -> dict:
    """basename -> [repo-relative paths] for every file under root, skipping .git.

    Class 2b reads this for existence only (truthiness of the list) and does not
    disambiguate a basename collision — see the docstring's class-2b note. Class 2c reads
    the stored paths to answer the strictly narrower question "does any file in the repo
    end with THIS multi-segment path?" (repo_has_path_suffix), which is the same fallback
    generalised from one segment to n."""
    index: dict = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        prefix = "" if rel_dir == "." else rel_dir + "/"
        for fn in filenames:
            index.setdefault(fn, []).append(prefix + fn)
    return index


def repo_has_path_suffix(index: dict, token: str) -> bool:
    """True if some file in the repo has `token` as a whole-segment path suffix.

    The class-2b basename fallback, generalised: for a single-segment token this is exactly
    "does this basename exist anywhere", and for `a/b/c.json` it demands the whole a/b/c.json
    tail, not just c.json. That extra strictness is what lets class 2c still catch
    `paper_falqon/manuscript/main.pdf` even though other `main.pdf` files exist in the tree."""
    for candidate in index.get(token.rsplit("/", 1)[-1], ()):
        if candidate == token or candidate.endswith("/" + token):
            return True
    return False


# ---------------------------------------------------------------------------
# Fenced-code "example" spans
# ---------------------------------------------------------------------------

def example_fence_lines(lines: list) -> set:
    """Return the set of 1-based line numbers that sit inside a fenced code block whose
    fence is marked as an example (info-string says so, or the preceding non-blank line
    does)."""
    skip = set()
    in_fence = False
    is_example = False
    fence_char = None
    last_nonblank = ""
    for i, raw in enumerate(lines, start=1):
        m = FENCE_RE.match(raw)
        if m:
            marker, info = m.group(2), m.group(3)
            this_char = marker[0]
            if not in_fence:
                in_fence = True
                fence_char = this_char
                is_example = "example" in info.lower() or "example" in last_nonblank.lower()
            elif this_char == fence_char:
                in_fence = False
                is_example = False
                fence_char = None
            if raw.strip():
                last_nonblank = raw
            continue
        if in_fence and is_example:
            skip.add(i)
        if raw.strip():
            last_nonblank = raw
    return skip


def url_spans(line: str):
    return [m.span() for m in URL_RE.finditer(line)]


def in_any_span(pos: int, spans) -> bool:
    return any(a <= pos < b for a, b in spans)


def looks_illustrative(text: str) -> bool:
    return "<" in text or ">" in text or "*" in text or "..." in text


def has_illustrative_neighbor(line: str, start: int, end: int) -> bool:
    """True if the character immediately before/after the match span is a glob or
    ellipsis marker that sits just outside the matched text itself (see
    ADJACENT_ILLUSTRATIVE_CHARS)."""
    before = line[start - 1] if start > 0 else ""
    after = line[end] if end < len(line) else ""
    return before in ADJACENT_ILLUSTRATIVE_CHARS or after in ADJACENT_ILLUSTRATIVE_CHARS


def is_negated_claim(line: str, match_start: int) -> bool:
    window = line[max(0, match_start - NEGATION_WINDOW):match_start]
    return bool(NEGATION_RE.search(window)) or bool(GITIGNORED_RE.search(line))


def is_backticked(line: str, start: int, end: int) -> bool:
    return start > 0 and end < len(line) and line[start - 1] == "`" and line[end] == "`"


# ---------------------------------------------------------------------------
# Class 1: sibling assertions
# ---------------------------------------------------------------------------

def _dir_has_match_for_keyword(directory: Path, self_name: str, keyword: str) -> bool:
    keyword = keyword.lower()
    try:
        siblings = [p.name for p in directory.iterdir() if p.is_file() and p.name != self_name]
    except OSError:
        siblings = []
    if keyword in FORMAT_WORDS:
        ext = keyword.lstrip(".")
        return any(name.lower().endswith("." + ext) for name in siblings)
    return any(keyword in name.lower() for name in siblings)


def check_sibling_assertions(rel_path: str, abs_path: Path, lines: list, skip_lines: set, repo_root: Path) -> list:
    gaps = []
    directory = abs_path.parent
    self_name = abs_path.name
    for lineno, raw in enumerate(lines, start=1):
        if lineno in skip_lines:
            continue
        line = raw.rstrip("\n")
        sib_m = SIBLING_RE.search(line)
        if not sib_m:
            continue
        if is_negated_claim(line, sib_m.start()):
            continue
        spans = url_spans(line)

        # Prefer an explicit filename named on the same line, if any — and if several
        # are named, the one nearest the proximity phrase (not just the first in the
        # line: a line can name an unrelated file earlier, e.g. "Decision point: D1
        # (EIGEN_STRATEGY.md). Extraction: extraction.md beside this file." — the
        # sibling claim is about extraction.md, not EIGEN_STRATEGY.md; picking the
        # first token in the line was a false positive caught in the PROVE run).
        candidates = [
            m for m in FILENAME_TOKEN_RE.finditer(line)
            if not in_any_span(m.start(), spans)
            and not looks_illustrative(m.group(1))
            and not has_illustrative_neighbor(line, m.start(), m.end())
        ]
        explicit = None
        if candidates:
            explicit = min(candidates, key=lambda m: abs(m.start() - sib_m.start())).group(1)

        if explicit is not None:
            # "beside this file" / "in this directory" asserts same-directory placement,
            # so the explicit name (bare or itself a relative fragment) is resolved from
            # the claiming file's own directory.
            target = directory / explicit
            if not target.exists():
                missing = str(target.relative_to(repo_root)) if _is_within(target, repo_root) else str(target)
                gaps.append(Gap(
                    file=rel_path, line=lineno, claim_class="sibling_assertion",
                    excerpt=line.strip()[:160], missing=missing,
                ))
            continue

        # No explicit filename: generic keyword claim ("raw transcript beside this file").
        noun_m = FILE_NOUN_RE.search(line)
        if not noun_m:
            continue
        keyword = noun_m.group(1)
        if _dir_has_match_for_keyword(directory, self_name, keyword):
            continue
        rel_dir = directory.relative_to(repo_root)
        gaps.append(Gap(
            file=rel_path, line=lineno, claim_class="sibling_assertion",
            excerpt=line.strip()[:160],
            missing=f"{rel_dir}/*{keyword.lower()}* (no matching file in directory)",
        ))
    return gaps


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Class 2b directory attribution
# ---------------------------------------------------------------------------

def _dir_tokens(line: str, spans) -> list:
    """Directory tokens on a line, as (start, text), skipping URLs and glob-ish text.

    Backticked only. Bare slash runs in prose are alternation, not paths — "debt
    before/after/Δ" (CENSUS_2026-07-21 line 76) was attributed as a directory in the
    first run of this repair and put a bare filename at `before/after/pipeline-8778.png`.
    Every genuine directory mention observed in this corpus is backticked, the same
    reasoning that gates CODE_EXTENSIONS."""
    out = []
    for m in DIR_TOKEN_RE.finditer(line):
        text = m.group(1)
        if in_any_span(m.start(), spans) or looks_illustrative(text):
            continue
        if not is_backticked(line, m.start(), m.end()):
            continue
        out.append((m.start(), text))
    return out


def paragraph_carried_dirs(lines: list) -> dict:
    """lineno -> the last directory token seen on an EARLIER line of the same paragraph
    (a run of non-blank lines), or None. Step (ii) of directory attribution."""
    carried = {}
    current = None
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        if not line.strip():
            current = None
            carried[lineno] = None
            continue
        carried[lineno] = current
        toks = _dir_tokens(line, url_spans(line))
        if toks:
            current = toks[-1][1]
    return carried


def attributed_dir(line: str, match_start: int, spans, carried) -> str:
    """Steps (i) then (ii): nearest directory token earlier on this line, else the
    directory carried in from earlier in the paragraph. None if neither."""
    same_line = [t for (pos, t) in _dir_tokens(line, spans) if pos < match_start]
    if same_line:
        return same_line[-1]
    return carried


def declared_dir_map(lines: list, skip_lines: set, carried_map: dict) -> dict:
    """basename -> directory, from every bare filename this document places somewhere by
    attribution steps (i)/(ii). First declaration wins. Step (iii) reads this map."""
    declared = {}
    for lineno, raw in enumerate(lines, start=1):
        if lineno in skip_lines:
            continue
        line = raw.rstrip("\n")
        spans = url_spans(line)
        for m in BARE_FILENAME_RE.finditer(line):
            text = m.group(1)
            if in_any_span(m.start(), spans) or looks_illustrative(text):
                continue
            if has_illustrative_neighbor(line, m.start(), m.end()):
                continue
            d = attributed_dir(line, m.start(), spans, carried_map.get(lineno))
            if d and text not in declared:
                declared[text] = d
    return declared


# ---------------------------------------------------------------------------
# Class 2: explicit relative path references
# ---------------------------------------------------------------------------

def check_explicit_paths(rel_path: str, abs_path: Path, lines: list, skip_lines: set, basename_index: dict, repo_root: Path) -> list:
    gaps = []
    directory = abs_path.parent
    seen = set()  # (line, matched_text) dedupe within a line for overlapping regexes
    carried_map = paragraph_carried_dirs(lines)
    declared = declared_dir_map(lines, skip_lines, carried_map)

    for lineno, raw in enumerate(lines, start=1):
        if lineno in skip_lines:
            continue
        line = raw.rstrip("\n")
        spans = url_spans(line)

        is_table_row = bool(TABLE_ROW_RE.match(line))

        for m in REPO_RELATIVE_RE.finditer(line):
            text = m.group(1)
            if in_any_span(m.start(), spans) or looks_illustrative(text):
                continue
            if has_illustrative_neighbor(line, m.start(), m.end()):
                continue
            if is_negated_claim(line, m.start()):
                continue
            key = (lineno, text)
            if key in seen:
                continue
            seen.add(key)
            if text.startswith("evidence/"):
                target = repo_root / text
            else:  # ./... or ../...
                target = directory / text
            if not target.exists():
                resolved = str(target.resolve())
                if _is_within(target.resolve(), repo_root):
                    resolved = str(target.resolve().relative_to(repo_root))
                scratch = is_scratch_path(resolved)
                if scratch:
                    severity, missing = "note", text
                else:
                    severity, missing = regenerable_severity(text, target.resolve(), repo_root)
                gaps.append(Gap(
                    file=rel_path, line=lineno,
                    claim_class="scratch_reference" if scratch else "explicit_path",
                    excerpt=line.strip()[:160], missing=missing,
                    severity=severity,
                ))

        # Class 2c: any other directory prefix. Backticked only, and only after the
        # own-directory, repo-root and repo-wide path-suffix checks have all missed.
        for m in PREFIXED_RELATIVE_RE.finditer(line):
            text = m.group(1)
            if in_any_span(m.start(), spans) or looks_illustrative(text):
                continue
            if has_illustrative_neighbor(line, m.start(), m.end()):
                continue
            if is_negated_claim(line, m.start()):
                continue
            # Backticked only — see the class-2c note in the module docstring. An
            # unbackticked slash run in prose is alternation or a fragment of a path this
            # regex cannot spell (a directory name containing a space).
            if not is_backticked(line, m.start(), m.end()):
                continue
            key = (lineno, text)
            if key in seen:
                continue
            seen.add(key)
            # Resolution order: the claiming file's own directory first, then the repo root.
            if (directory / text).exists() or (repo_root / text).exists():
                continue
            # Repo-wide fallback, the class-2b rule generalised to n segments.
            if repo_has_path_suffix(basename_index, text):
                continue
            scratch = is_scratch_path(text)
            where = (
                "scratch/working dir — expected-ephemeral, stale citation" if scratch
                else "not found anywhere in repo"
            )
            base_missing = f"{text} ({where})"
            if scratch:
                severity, missing = "note", base_missing
            else:
                # Resolved against the repo root — the canonical reading for a
                # multi-segment prefixed path once own-directory/repo-root/path-suffix
                # have all missed (see class 2c in the module docstring).
                severity, missing = regenerable_severity(base_missing, repo_root / text, repo_root)
            gaps.append(Gap(
                file=rel_path, line=lineno,
                claim_class="scratch_reference" if scratch else "explicit_path",
                excerpt=line.strip()[:160],
                missing=missing,
                severity=severity,
            ))

        for m in BARE_FILENAME_RE.finditer(line):
            text = m.group(1)
            if in_any_span(m.start(), spans) or looks_illustrative(text):
                continue
            if has_illustrative_neighbor(line, m.start(), m.end()):
                continue
            if is_negated_claim(line, m.start()):
                continue
            ext = text.rsplit(".", 1)[-1].lower()
            backticked = is_backticked(line, m.start(), m.end())
            if ext in CODE_EXTENSIONS and not backticked:
                continue
            # Bare (non-backticked) filenames inside a table cell are routinely used as
            # row labels/nicknames, not path claims — see TABLE_ROW_RE above.
            if is_table_row and not backticked:
                continue
            key = (lineno, text)
            if key in seen:
                continue
            seen.add(key)

            # Directory attribution: where does the prose say this file lives?
            claimed_dir = attributed_dir(line, m.start(), spans, carried_map.get(lineno))
            if claimed_dir is None:
                claimed_dir = declared.get(text)

            if claimed_dir is not None:
                base = directory if claimed_dir.startswith(("./", "../")) else repo_root
                if (base / claimed_dir / text).exists():
                    continue
            # The own-directory and repo-wide checks still run whatever the attribution
            # said, so attribution can never manufacture a gap (see module docstring).
            if (directory / text).exists():
                continue
            if basename_index.get(text):
                continue

            if claimed_dir is not None:
                claimed_rel = os.path.normpath(
                    str(directory.relative_to(repo_root) / claimed_dir / text)
                    if claimed_dir.startswith(("./", "../"))
                    else f"{claimed_dir}{text}"
                )
            else:
                claimed_rel = f"{directory.relative_to(repo_root)}/{text}"
            # All three checks (claimed dir, own dir, repo-wide basename) failed here.
            where = "not found anywhere in repo"
            scratch = is_scratch_path(claimed_rel)
            if scratch:
                where = "scratch/working dir — expected-ephemeral, stale citation"
            base_missing = f"{claimed_rel} ({where})"
            if scratch:
                severity, missing = "note", base_missing
            else:
                severity, missing = regenerable_severity(
                    base_missing, repo_root / claimed_rel, repo_root
                )
            gaps.append(Gap(
                file=rel_path, line=lineno,
                claim_class="scratch_reference" if scratch else "explicit_path",
                excerpt=line.strip()[:160],
                missing=missing,
                severity=severity,
            ))
    return gaps


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def audit(evidence_dir: Path, repo_root: Path) -> list:
    basename_index = build_basename_index(repo_root)
    gaps: list = []
    for md_path in sorted(evidence_dir.rglob("*.md")):
        rel_path = str(md_path.relative_to(repo_root))
        text = md_path.read_text(encoding="utf-8", errors="replace")
        lines = text.split("\n")
        skip_lines = example_fence_lines(lines)
        gaps.extend(check_sibling_assertions(rel_path, md_path, lines, skip_lines, repo_root))
        gaps.extend(check_explicit_paths(rel_path, md_path, lines, skip_lines, basename_index, repo_root))

    # Dedupe: the same (file, line, missing) can legitimately fire from both classes
    # (e.g. a sibling-assertion line that also matches the bare-filename regex).
    deduped = []
    seen_keys = set()
    for g in gaps:
        key = (g.file, g.line, g.missing)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(g)
    # gaps first, then regenerable, then scratch notes; each block sorted by file/line.
    severity_rank = {"gap": 0, "regenerable": 1, "note": 2}
    deduped.sort(key=lambda g: (severity_rank.get(g.severity, 3), g.file, g.line))
    return deduped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit typed rows as JSON")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repo root (default: script's parent's parent)")
    parser.add_argument(
        "--strict", action="store_true",
        help="count scratch_reference notes and regenerable rows toward the exit status "
             "as well as gaps",
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    evidence_dir = repo_root / "evidence"
    if not evidence_dir.is_dir():
        print(f"no evidence/ directory at {evidence_dir}", file=sys.stderr)
        return 1

    rows = audit(evidence_dir, repo_root)
    gaps = [g for g in rows if g.severity == "gap"]
    regenerable = [g for g in rows if g.severity == "regenerable"]
    scratch_notes = [g for g in rows if g.severity == "note"]
    non_gap = regenerable + scratch_notes  # what --strict adds to the failure count

    if args.json:
        print(json.dumps([asdict(g) for g in rows], indent=2))
    else:
        if not rows:
            print("audit_evidence_claims: 0 gaps.")
        else:
            widths = (
                max(len(f"{g.file}:{g.line}") for g in rows),
                max(len(g.severity) for g in rows),
                max(min(len(g.excerpt), 70) for g in rows),
            )

            def emit(block):
                for g in block:
                    loc = f"{g.file}:{g.line}"
                    excerpt = g.excerpt if len(g.excerpt) <= 70 else g.excerpt[:67] + "..."
                    print(
                        f"{loc.ljust(widths[0])} | {g.severity.ljust(widths[1])} | "
                        f"{excerpt.ljust(widths[2])} | {g.missing}"
                    )

            if gaps:
                print("GAPS (the committed record does not hold):")
                emit(gaps)
            if regenerable:
                if gaps:
                    print()
                print(
                    "REGENERABLE (deliberately absent — gitignored on purpose; "
                    "re-render to re-open):"
                )
                emit(regenerable)
            if scratch_notes:
                if gaps or regenerable:
                    print()
                print("NOTES (scratch/working-dir citations — expected-ephemeral, not gaps):")
                emit(scratch_notes)
            print(
                f"\naudit_evidence_claims: {len(gaps)} gap(s), {len(regenerable)} "
                f"regenerable, {len(scratch_notes)} scratch note(s)."
            )

    return 1 if (gaps or (args.strict and non_gap)) else 0


if __name__ == "__main__":
    sys.exit(main())
