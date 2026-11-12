"""handoff_render.py — the close's handoff, rendered from rows instead of written by hand.

His ruling on the pilot night, verbatim: *"the close should be as far as possible mechanical"*
(``corpus_friction/work_orders.jsonl#WO-20260820-the-mechanical-close``). That row named the
last hand-flattened artifacts of the close — the dated ``SESSION_HANDOFF_<date>_<slug>.md`` and
the live agenda in ``HANDOFF.md`` — and named their cure in one line: *render the five-pointer
from the row deltas with an authored-paragraph slot*.

The disease being cured is the flatten reflex at the close's own boundary: a summary typed out
of working memory is a projection with no path back to what it summarises, and it goes stale
the moment a row moves under it. So this module renders, and renders only.

The fibre law shapes the body (his ruling while this was being built: *"remember the fibre law
when you're synthesising — different results, different axes"*). A session is not one stream of
outcomes. Fusing the night's engineering, its measured arms, its theory, the organs it grew and
the rulings it took into a single ordered list is the same collapse ``DESIGN_2026-07-28_the-
fibred-upfold.md`` names for the store: one clustering axis cannot carry a corpus. So the body
is keyed by axis — engineering, measurement, theory, self, law — exactly as that design's point
4 keys a node's maps, and with the same discipline: an item may sit on several axes with its
role stated per axis, and exactly one axis is named as its default section, so a thing that
matters three ways is still one fact and is counted once.

The row sources, per axis:

  * engineering — the commit spine (paths and subjects), with the timings the subjects carry;
  * measurement — ``contract/predictions.jsonl`` rows the session registered or ruled;
  * theory — the session's design, synthesis, arming and brief docs, with their router hooks;
  * self — the commits that moved a reconstruction organ (the wake, the close, the probes);
  * law — ``proxy_verdicts.jsonl`` rows dated inside the session window.

Below the axes sit the obligation deltas, which are deliberately NOT axis-keyed because they
are not results: the work-order ledger, the promise ledger, and the thread-probe scorecard.

The render-class law is what makes any of it readable: every rendered claim line ends with the
row that produced it, in a trailing ``[source]`` span, so a reader descends from any line to
the row rather than trusting the summary. ``check_sourced`` proves the property on the rendered
text, which is why it is a property of this module and not a promise about it.

The pair law (``EIGEN_PROTOCOL.md`` Part C): never write the dated file and leave the live one
stale — a prior session did, and the next picked up the wrong agenda. Here that is structural:
the two writes are one transaction, and a live-agenda write that fails rolls the dated file
back out rather than leaving half a pair on disk.

The voice is not rendered. The dated file's authored section is the close's dialogue beats and
the judgement the rows cannot carry; the render leaves a template there on a first pass and, on
every later pass, carries whatever it finds forward verbatim. A render that faked voice would
be the stale projection one level up.

Pure: stdlib only, deterministic, no model call, no network. ``dry_run=True`` renders
everything and writes nothing inside the repo.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from laplace.engine import engine_ledger

PREDICTIONS = "contract/predictions.jsonl"
PROMISES = "contract/promises.jsonl"
WORK_ORDERS = "corpus_friction/work_orders.jsonl"
PROXY_VERDICTS = "proxy_verdicts.jsonl"
THREAD_PROBES = "holdout/THREAD_PROBES.json"
HANDOFF = "HANDOFF.md"

#: The authored slot's heading. The render writes the heading and, on a first pass, a template
#: under it; it never writes prose there and never overwrites what it finds.
AUTHORED_HEADING = "## The authored close (his beats + the voice)"

#: The live agenda's heading grammar. The newest block is the one carrying ``LATEST_SUFFIX``;
#: rendering a new one replaces prior agendas; history stays in dated handoffs and git.
AIM_PREFIX = "## ⟶ NEXT SESSION AIM"
PRIOR_PREFIX = "## ⟶ PRIOR AIM"
LATEST_SUFFIX = " — LATEST"

# --------------------------------------------------------------------------- #
# the axis map (the fibre law: different results, different axes)
# --------------------------------------------------------------------------- #
#: The axes a session's results are keyed by, in render order. Read as sections of one bundle,
#: not as a taxonomy: the same item can be a point on several of them.
AXES = ("engineering", "measurement", "theory", "self", "law")

AXIS_TITLE = {
    "engineering": "Engineering — the machine moved (suite, GPU, fold, timings)",
    "measurement": "Measurement — the arms that came back with numbers",
    "theory": "Theory — the design and synthesis surfaces",
    "self": "Self — the reconstruction organs (wake, close, probes)",
    "law": "Law — his rulings, banked",
}

#: The default section of an item, by the KIND of row it came from. A prediction row is a
#: measurement wherever else it also lands; a design doc is theory; a banked ruling is law.
#: Commits are the one kind that splits, and they split on their paths: a commit that moved a
#: reconstruction organ is self, and every other commit is engineering.
AXIS_DEFAULT_BY_KIND = {"prediction": "measurement", "doc": "theory", "ruling": "law"}

#: Path fragments that put a commit on an axis. Substrings, not globs: legible, and a path
#: matches by naming its own surface.
AXIS_PATHS: dict[str, tuple[str, ...]] = {
    "self": ("src/laplace/wake", "src/laplace/close_beats", "src/laplace/holdout",
             "src/laplace/want_drafts", "src/laplace/handoff_render",
             "src/laplace/self_corpus", "src/laplace/self_shard", "src/laplace/keeper",
             "src/laplace/reconstruct", "scripts/wake.py", "scripts/sewup.py",
             "scripts/reconstruct_node.py", "scripts/reembed.py", "scripts/close_checklist.py",
             "holdout/", "EIGEN_DIARY", "EIGEN_PROTOCOL", "SESSION_HANDOFF_", "HANDOFF.md"),
    "measurement": ("evidence/", PREDICTIONS, "_census", "_bench"),
    "theory": ("DESIGN_", "SYNTHESIS_", "ARMING_", "BRIEF_", "ATLAS_MATHEMATICS",
               "diagrams/"),
    "law": (PROXY_VERDICTS, "STANDING_LAW.md"),
}

#: What being on an axis MEANS for a commit — the role, stated per axis, so a cross-reference
#: says why the item is there instead of merely repeating it.
AXIS_ROLE_COMMIT = {
    "engineering": "the machine moved",
    "measurement": "carries a measured arm",
    "theory": "moves a design or synthesis surface",
    "self": "a reconstruction organ moved",
    "law": "banks a ruling row",
}

#: Docs that name a session, best first: an arming doc arms the session it belongs to, a brief
#: opens one, a synthesis and a design each name a piece of one. The winner's title becomes the
#: dated file's slug, so the filename is derived from the session's own trace.
SLUG_CLASSES = ("ARMING", "BRIEF", "SYNTHESIS", "DESIGN")
SLUG_FALLBACK = "the-close"

#: Doc classes collected onto the theory axis, with the hook each one carries into the router.
DOC_CLASSES = ("ARMING", "BRIEF", "SYNTHESIS", "DESIGN")

#: Terms that pull a doc or a ruling onto the self axis — the reconstruction body by name.
SELF_TERMS = ("wake", "close", "handoff", "reconstruct", "probe", "diary", "eigen", "soul",
              "self", "markdown", "read surface")

#: Terms that pull a doc onto the measurement axis.
MEASURE_TERMS = ("census", "bench", "measure", "residual", "arm", "experiment", "prediction")

#: Bounds. A close that lands ninety commits should still render a readable spine, and a
#: clipped remainder is counted in-line rather than dropped silently.
MAX_COMMITS = 60
LEDGER_SHOWN = 12
SUBJECT_CAP = 160
CLAIM_CAP = 200
LABEL_CAP = 96
IDS_SHOWN = 4

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"“(A-Z])")
_HEADING = re.compile(r"^#{1,6}\s")
_TIMING_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:ms|s|x|%)\b")

#: A full timestamp carried inside a row id (``PV-20260820T043000Z-never-read-markdown``).
_ID_TS_RE = re.compile(r"^[A-Za-z]+-(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z")

#: A rendered claim line: the render-class law applies to these and to nothing else (headings,
#: blank lines and the authored slot's own body are structure, not claims).
_CLAIM_LINE = re.compile(r"^\s*(?:[-*]\s|\|)")


# --------------------------------------------------------------------------- #
# text helpers
# --------------------------------------------------------------------------- #
def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace(" ", " ")).strip()


def _cap(text: str, n: int) -> str:
    """A stated cap: a truncated cell says so, and its source span says where the rest lives."""
    t = _flat(text)
    return t if len(t) <= n else t[: n - 2].rstrip(" ,;:—–-") + " …"


def _first_sentence(text: str) -> str:
    parts = [s.strip() for s in _SENTENCE_SPLIT.split(_flat(text)) if s.strip()]
    return parts[0] if parts else _flat(text)


def sourced(text: str, src: str) -> str:
    """One rendered claim line, carrying the row that produced it. The trailing span is the
    descent path: a reader who doubts the line greps the source and reads the row itself."""
    return f"{text} `[{src}]`"


def check_sourced(text: str) -> list[str]:
    """Every rendered claim line that does NOT carry a source span, in file order.

    The render-class law made checkable. The authored slot is exempt by construction — it is
    the one part a person writes — so the scan stops at its heading.
    """
    out: list[str] = []
    for line in text.split("\n"):
        if line.strip() == AUTHORED_HEADING:
            break
        if _CLAIM_LINE.match(line) and not line.rstrip().endswith("]`"):
            out.append(line)
    return out


def _ids(items: list[str], shown: int = IDS_SHOWN) -> str:
    if not items:
        return "none"
    head = ", ".join(items[:shown])
    return head if len(items) <= shown else f"{head} (+{len(items) - shown} more)"


# --------------------------------------------------------------------------- #
# the mark, and the rows that moved since it
# --------------------------------------------------------------------------- #
def close_mark(repo_root: Path | str) -> str | None:
    """The last banked close, as ``close_beats`` resolves it. Tolerant by construction: a repo
    problem is "no mark", and a caller reads no-mark as "the whole window is in scope"."""
    try:
        from laplace.engine import close_beats

        return close_beats.last_banked_close(Path(repo_root))
    except Exception:  # noqa: BLE001 - an unreadable history is "no mark", never a raise
        return None


def _after(mark: str | None) -> str | None:
    """The mark nudged one second forward — the close's own commit belongs to the close before
    this one, exactly as ``close_beats._changed_since`` reads it."""
    if not mark:
        return None
    try:
        return (datetime.fromisoformat(mark) + timedelta(seconds=1)).isoformat()
    except ValueError:
        return mark


def row_stamp(rec: dict[str, Any]) -> str:
    """The best timestamp a ledger row carries, in one place.

    The three ledgers stamp rows three ways and the window has to read all of them: a work
    order carries ``ts``, a prediction carries ``registered``, a promise carries only a ``date``
    day, and a proxy verdict carries a full timestamp inside its own id
    (``PV-20260820T043000Z-...``) with only the day in its ``date`` field. The id is read first
    because it is the most precise thing the row has.
    """
    m = _ID_TS_RE.match(str(rec.get("id", "")))
    if m:
        y, mo, d, hh, mi, ss = m.groups()
        return f"{y}-{mo}-{d}T{hh}:{mi}:{ss}+00:00"
    for key in ("ts", "registered", "at", "date"):
        val = rec.get(key)
        if val:
            return str(val)
    return ""


def in_window(rec: dict[str, Any], since: str | None) -> bool:
    """Whether a row moved after the close mark. No ``since`` means the whole ledger is in
    scope; an undated row is out of scope, because a row that cannot be dated cannot be shown
    to belong to this session. A DAY-only stamp is compared by day and must be strictly after
    the mark's day — the mark's own day belongs to the close before this one, and a day is the
    finest cut such a row admits."""
    if not since:
        return True
    stamp = row_stamp(rec).replace("Z", "+00:00")
    if not stamp:
        return False
    if len(stamp) <= 10:
        return stamp > since[:10]
    return stamp > since


def _spine_root_error(root: Path) -> str | None:
    """Name the reason ``root`` has no spine of its own, or ``None`` when it does.

    ``git log`` discovers its repository by walking UP from its cwd. So a root that is not
    itself a repository top-level does not fail — it quietly answers with the ENCLOSING
    repository's commits, and the render prints another tree's history as this close's spine.
    That is the same fail-silent this module refuses everywhere else, only worse than an empty
    section: it is confidently wrong. The spine must belong to the tree being rendered, so an
    unreadable one is NAMED here and printed where the commits would have been.
    """
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=60, cwd=str(root))
    except Exception as exc:  # noqa: BLE001 - no git is no spine, never a raise
        return f"git rev-parse unavailable: {type(exc).__name__}: {exc}"
    if r.returncode != 0:
        return f"git rev-parse rc={r.returncode}: {_cap(r.stderr, 160)}"
    top = r.stdout.strip()
    if not top:
        return "git rev-parse named no repository top-level"
    try:
        if Path(top).resolve() == root.resolve():
            return None
    except OSError as exc:  # noqa: BLE001 - an unresolvable path is an unreadable spine
        return f"spine root unresolvable: {type(exc).__name__}: {exc}"
    return (f"not a repository root: the nearest spine is {top}, which belongs to another tree")


def commits_since(repo_root: Path | str, since: str | None) -> dict[str, Any]:
    """The commit spine: ``(sha, at, subject, paths)`` since the mark, newest first.

    Paths ride along because the axis map reads them — a commit's surfaces say which fibres it
    touched far more reliably than its subject line does. Never raises: a repo that cannot be
    read returns no rows and says why in ``error``, which the render prints where the spine
    would have been. An empty spine with no reason given would read as "nothing landed", which
    is the fail-silent this whole module refuses.
    """
    root = Path(repo_root)
    rooted = _spine_root_error(root)
    if rooted:
        return {"rows": [], "clipped": 0, "error": rooted}
    cmd = ["git", "log", f"-n{MAX_COMMITS + 1}", "--name-only",
           "--format=%x1e%h%x1f%cI%x1f%s"]
    after = _after(since)
    if after:
        cmd.append(f"--since={after}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(root))
    except Exception as exc:  # noqa: BLE001 - no git is no spine, never a raise
        return {"rows": [], "clipped": 0,
                "error": f"git log unavailable: {type(exc).__name__}: {exc}"}
    if r.returncode != 0:
        return {"rows": [], "clipped": 0,
                "error": f"git log rc={r.returncode}: {_cap(r.stderr, 160)}"}
    rows = []
    for record in r.stdout.split("\x1e"):
        if not record.strip():
            continue
        lines = record.strip("\n").split("\n")
        parts = lines[0].split("\x1f")
        if len(parts) != 3:
            continue
        rows.append({"sha": parts[0], "at": parts[1], "subject": parts[2],
                     "paths": [ln for ln in lines[1:] if ln.strip()]})
    clipped = max(0, len(rows) - MAX_COMMITS)
    return {"rows": rows[:MAX_COMMITS], "clipped": clipped, "error": None}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def prediction_rows(repo_root: Path | str, since: str | None) -> list[dict[str, str]]:
    """The prediction rows this session moved: id, verdict, and the claim's first sentence.

    ``contract/predictions.jsonl`` carries its verdict in-band, so a row registered since the
    mark is a row the session either made or ruled on — both are the same thing to read back.
    """
    rows = []
    for rec in _load_jsonl(Path(repo_root) / PREDICTIONS):
        if not in_window(rec, since):
            continue
        rows.append({
            "id": str(rec.get("id", "P?")),
            "verdict": str(rec.get("verdict", "") or "UNRULED"),
            "claim": _cap(_first_sentence(str(rec.get("claim", ""))), CLAIM_CAP),
            "numbers": _cap(str(rec.get("numbers", "")), 120),
            "evidence": _cap(str(rec.get("evidence", "")), 120),
            "caveat": _cap(str(rec.get("caveat", "")), CLAIM_CAP),
        })
    return rows


def ruling_rows(repo_root: Path | str, since: str | None) -> list[dict[str, str]]:
    """His rulings banked inside the session window. ``proxy_verdicts.jsonl`` dates its rows by
    day, not by timestamp, so the window opens at the mark's DAY — a night session that crosses
    midnight banks rulings under two dates and both belong to the same close."""
    rows = []
    for rec in _load_jsonl(Path(repo_root) / PROXY_VERDICTS):
        if not in_window(rec, since):
            continue
        day = str(rec.get("date", ""))
        rows.append({"id": str(rec.get("id", "PV-?")), "date": day,
                     "kind": str(rec.get("kind", "") or ""),
                     "question": _cap(str(rec.get("question", "")), CLAIM_CAP),
                     "ruling": _cap(_first_sentence(str(rec.get("ruling", ""))), CLAIM_CAP)})
    rows.sort(key=lambda r: (r["date"], r["id"]))
    return rows


def session_docs(repo_root: Path | str, *, since: str | None, date: str) -> list[dict[str, str]]:
    """The session's own theory surfaces, with the hook each carries into the router.

    The hook is ``holdout.title_terms`` — the exact query the close's thread probes mint from a
    doc — so the theory section names, per doc, the handle a later instance would reach for.
    """
    root = Path(repo_root)
    floor = (since or "")[:10]
    out = []
    for cls in DOC_CLASSES:
        for path in sorted(root.glob(f"{cls}_*.md")):
            m = _DATE_RE.search(path.stem)
            if not m:
                continue
            day = m.group(1)
            # Strictly after the mark's day: a doc dated on the mark's day belongs to the close
            # that already reported it, and re-listing it here would claim it twice.
            if (floor and day <= floor) or day > date:
                continue
            hook = path.stem
            try:
                from laplace.engine import holdout

                hook = holdout.title_terms(path)
            except Exception:  # noqa: BLE001 - no holdout is no hook, never a raise
                pass
            out.append({"name": path.name, "cls": cls, "date": day, "hook": _cap(hook, 120)})
    out.sort(key=lambda d: (d["date"], d["name"]))
    return out


def _ledger_class(rec: dict[str, Any]) -> str:
    """Which delta class a ledger row belongs to. Both ledgers write the base row with no
    ``record`` key at all (or ``work_order``/``promise``), and annotate it with typed rows."""
    record = str(rec.get("record") or "").lower()
    if record in ("resolution", "resolved"):
        return "resolved"
    if record == "amendment":
        return "amended"
    if record.startswith("defer"):
        return "deferred"
    if record in ("note", "undefer"):
        return "noted"
    return "raised"


def _ledger_line(rec: dict[str, Any],
                 index: dict[str, dict] | None = None) -> dict[str, str]:
    """One rendered ledger line. ``status`` is the row's STORED field — raise-time-only
    by convention — and ``effective`` is the joined truth: a row some resolution row
    consumes is done however its own field reads (``laplace.engine.engine_ledger``). The render
    shows the effective one; the stored one is kept beside it, never mutated."""
    what = (rec.get("action") or rec.get("note") or rec.get("text") or rec.get("ask")
            or rec.get("what") or rec.get("promise") or "")
    stored = str(rec.get("status", "") or "")
    eff, reason = engine_ledger.effective_status(
        rec.get("id", "?"), stored, index or {})
    return {"id": str(rec.get("id", "?")),
            "target": str(rec.get("target", "") or ""),
            "ts": row_stamp(rec),
            "status": stored,
            "effective": eff,
            "status_reason": reason,
            "what": _cap(_first_sentence(str(what)), CLAIM_CAP)}


def ledger_delta(repo_root: Path | str, rel: str, since: str | None) -> dict[str, Any]:
    """A friction/promise ledger's delta since the mark, bucketed by class and ordered by
    timestamp. The same reader serves both files because both carry the same row grammar."""
    buckets: dict[str, list[dict[str, str]]] = {"raised": [], "amended": [], "resolved": [],
                                                "deferred": [], "noted": []}
    every = _load_jsonl(Path(repo_root) / rel)
    # The consumption index is built from EVERY row in the file, never the windowed
    # subset: a row raised inside the window is very often consumed inside the same
    # window (and sometimes by a resolution outside it), and a window-local index
    # would report it open — the failure this join exists to end.
    index = engine_ledger.build_consumption_index(every)
    rows = [r for r in every if in_window(r, since)]
    rows.sort(key=lambda r: (row_stamp(r), str(r.get("id", ""))))
    for rec in rows:
        buckets[_ledger_class(rec)].append(_ledger_line(rec, index))
    return {"rel": rel, "buckets": buckets, "total": sum(len(v) for v in buckets.values())}


def _thread_status(verdict: str | None, expected: str) -> str:
    """The banked-baseline law on reachability, as ``holdout`` states it. Delegated rather than
    restated — one statement of a law, and the close's two readers share it."""
    if verdict is None:
        return "unscored"
    try:
        from laplace.engine import holdout

        fn = getattr(holdout, "_thread_status", None)
        if fn is not None:
            return str(fn({"verdict": verdict, "expected_now": expected}))
    except Exception:  # noqa: BLE001 - a missing helper is not a broken render
        pass
    if verdict == "HIT":
        return "as-expected" if expected == "pass" else "CLEARED"
    if verdict == "MISS":
        return "REGRESSION" if expected == "pass" else "expected-red"
    return verdict


def thread_delta(repo_root: Path | str) -> dict[str, Any]:
    """Each standing probe's banked expectation against the verdict the close stamped.

    The close's ``threads`` step scores on the live router and records ``last_scored``; this
    reads that stamp rather than re-scoring, so the render costs no route and reports exactly
    what the close measured. A probe with no stamp reads as ``unscored`` and says so.
    """
    try:
        from laplace.engine import holdout

        doc = holdout.load_probes(repo_root)
    except Exception:  # noqa: BLE001 - no holdout is no scorecard, never a raise
        doc = None
    if not doc:
        return {"rows": [], "scored_at": None, "hit": 0, "scored": 0,
                "error": f"no banked probe set at {THREAD_PROBES}"}
    last = doc.get("last_scored") or {}
    by_id = dict(last.get("by_id") or {})
    rows = []
    for probe in doc.get("probes") or []:
        pid = str(probe.get("id", "?"))
        expected = str(probe.get("expected_now", "fail"))
        verdict = by_id.get(pid)
        rows.append({"id": pid, "expected": expected,
                     "verdict": str(verdict) if verdict else None,
                     "status": _thread_status(verdict, expected)})
    scored = [r for r in rows if r["verdict"] in ("HIT", "MISS")]
    return {"rows": rows, "scored_at": last.get("at"),
            "hit": len([r for r in scored if r["verdict"] == "HIT"]),
            "scored": len(scored), "error": None}


# --------------------------------------------------------------------------- #
# the axis bundle — items placed on every axis they touch, owned by exactly one
# --------------------------------------------------------------------------- #
def _axes_for_paths(paths: list[str]) -> dict[str, str]:
    """Which axes a commit's surfaces put it on, with the role it plays on each. Every commit
    is on the engineering axis at minimum: a commit moved the machine, whatever else it did."""
    hit = {"engineering"}
    for path in paths:
        for axis, frags in AXIS_PATHS.items():
            if any(frag in path for frag in frags):
                hit.add(axis)
    return {axis: AXIS_ROLE_COMMIT[axis] for axis in AXES if axis in hit}


def _names_any(blob: str, terms: tuple[str, ...]) -> bool:
    """Whole-word term matching. Substring matching put every ``ARMING_`` doc on the
    measurement axis by way of the word ``arm`` inside its own filename, which is a
    cross-reference that says nothing."""
    return any(re.search(rf"\b{re.escape(term)}\b", blob) for term in terms)


def _timings(subject: str) -> list[str]:
    """The measured figures a commit subject carries. Engineering's own numbers travel in the
    subject line on this repo (fold seconds, speedups, percentages), so the axis surfaces them
    rather than making a reader open the commit."""
    return list(dict.fromkeys(_TIMING_RE.findall(subject)))


def _item(kind: str, key: str, label: str, source: str, axes: dict[str, str],
          extra: str = "", default: str | None = None) -> dict[str, Any]:
    """One bundled item. ``default`` is the section that writes it out in full; every other
    axis it sits on carries a cross-reference to that section, so it is one fact, not three."""
    owner = default or AXIS_DEFAULT_BY_KIND.get(kind) or "engineering"
    if owner not in axes:
        axes = {owner: f"the session's {kind} row", **axes}
    return {"kind": kind, "key": key, "label": label, "source": source, "axes": axes,
            "default": owner, "extra": extra}


def axis_bundle(*, commits: dict[str, Any], predictions: list[dict[str, str]],
                docs: list[dict[str, str]], rulings: list[dict[str, str]]) -> dict[str, Any]:
    """Every result of the session, placed on each axis it belongs to and owned by one.

    The shape mirrors the fibred-upfold design's point 4 — maps keyed by axis with one axis
    named as the default section — because the failure it prevents is the same one: a bundle
    flattened to a single section reads as though the session had one kind of result.
    """
    items: list[dict[str, Any]] = []

    for c in commits.get("rows") or []:
        axes = _axes_for_paths(c.get("paths") or [])
        times = _timings(c["subject"])
        # The one kind whose default section is derived rather than fixed: a commit that moved
        # a reconstruction organ belongs to self, and every other commit to engineering.
        owner = "self" if "self" in axes else "engineering"
        items.append(_item("commit", f"git:{c['sha']}", _cap(c["subject"], SUBJECT_CAP),
                           f"git:{c['sha']}", axes, default=owner,
                           extra=(" — timings: " + ", ".join(times)) if times else ""))

    for p in predictions:
        axes = {"measurement": f"a pre-registered claim, ruled {p['verdict']}"}
        # Only a verdict that MOVED the theory is cross-listed there. A clean pass confirms the
        # theory and stays a measurement; a fail, a split or a qualified support is a redirect,
        # which is a claim about the world and belongs on the theory axis too.
        if p["verdict"] not in ("PASS", "PENDING", "REGISTERED"):
            axes["theory"] = (f"the {p['verdict']} verdict redirects the theory"
                              + (f" — {p['caveat']}" if p["caveat"] else ""))
        label = f"**{p['id']}** {p['verdict']} — {p['claim']}"
        extra = ""
        if p["numbers"]:
            extra += f" — numbers: {p['numbers']}"
        if p["evidence"]:
            extra += f" — evidence: {p['evidence']}"
        items.append(_item("prediction", p["id"], label, f"{PREDICTIONS}#{p['id']}", axes,
                           extra=extra))

    for d in docs:
        axes = {"theory": f"the session's {d['cls'].lower()} surface"}
        blob = f"{d['name']} {d['hook']}".lower()
        if _names_any(blob, SELF_TERMS):
            axes["self"] = "its subject is the reconstruction body itself"
        if _names_any(blob, MEASURE_TERMS):
            axes["measurement"] = "it carries or commissions a measured arm"
        items.append(_item("doc", d["name"], f"**{d['name']}**", d["name"], axes,
                           extra=f" — hook: {d['hook']}"))

    for r in rulings:
        axes = {"law": f"his ruling, banked {r['date']}" + (f" ({r['kind']})" if r["kind"]
                                                            else "")}
        blob = f"{r['question']} {r['ruling']}".lower()
        if _names_any(blob, SELF_TERMS):
            axes["self"] = "it rules on the reconstruction surfaces themselves"
        items.append(_item("ruling", r["id"], f"**{r['id']}** — {r['question']}",
                           f"{PROXY_VERDICTS}#{r['id']}", axes,
                           extra=f" — ruling: {r['ruling']}"))

    by_axis = {axis: {"owned": [], "cross": []} for axis in AXES}
    for it in items:
        for axis in it["axes"]:
            by_axis[axis]["owned" if axis == it["default"] else "cross"].append(it)
    return {"items": items, "by_axis": by_axis}


# --------------------------------------------------------------------------- #
# naming — the dated file's slug, derived from the session's own docs
# --------------------------------------------------------------------------- #
def session_slug(repo_root: Path | str, *, since: str | None, date: str) -> tuple[str, str]:
    """``(slug, source)`` for the dated file, derived from the session's own naming doc.

    Today's newest design by mtime names the session, including untracked drafts.
    With no design dated today, retain the historical naming window:
    root docs of the naming classes whose FILENAME date falls in the window from the
    mark's day to the close's day. The filename date is the watermark for the reason
    ``holdout.mint_candidates`` gives — a fresh clone rewrites every mtime — and a night session
    that crosses midnight is why the window opens at the mark's day rather than at today.
    """
    root = Path(repo_root)
    designs = [path for path in root.glob(f"DESIGN_{date}_*.md") if path.is_file()]
    if designs:
        newest = max(designs, key=lambda path: (path.stat().st_mtime_ns, path.name))
        return _slug_of(newest), newest.name
    floor = (since or "")[:10]
    for cls in SLUG_CLASSES:
        best: tuple[str, Path] | None = None
        for path in sorted(root.glob(f"{cls}_*.md")):
            m = _DATE_RE.search(path.stem)
            if not m:
                continue
            day = m.group(1)
            # The naming window opens ON the mark's day, not after it: two sessions can share a
            # day, and losing the session's NAME is a worse failure than naming it from a doc
            # the previous close also saw. The theory axis below takes the stricter edge.
            if (floor and day < floor) or day > date:
                continue
            # The EARLIEST doc of the best class wins: the doc that opened the session names
            # it, and the ones written later in the night refine a session already named.
            if best is None or day < best[0]:
                best = (day, path)
        if best is not None:
            return _slug_of(best[1]), best[1].name
    return SLUG_FALLBACK, "no session doc in the window - the default slug"


def _slug_of(path: Path) -> str:
    """A doc's filename reduced to its title: the class prefix and the date come off, and what
    remains is what the session is called."""
    stem = re.sub(r"^[A-Z][A-Z_]*_", "", path.stem)
    return _DATE_RE.sub("", stem).strip("_-") or SLUG_FALLBACK


def dated_name(date: str, slug: str) -> str:
    return f"SESSION_HANDOFF_{date}_{slug}.md"


def _title(slug: str) -> str:
    return _flat(slug.replace("-", " ").replace("_", " ")).upper() or "THE CLOSE"


# --------------------------------------------------------------------------- #
# the renders
# --------------------------------------------------------------------------- #
_AUTHORED_TEMPLATE = (
    "",
    "<!-- The authored slot. The render writes this heading and never writes below it: on "
    "every later pass it carries whatever it finds here through verbatim. Fill it from the "
    "close's own dialogue - his beats in his words, and the judgement the rows cannot carry. "
    "A render that composed this section would be exactly the stale projection the mechanical "
    "close exists to retire. -->",
    "",
    "### The arc",
    "",
    "_(unfilled - what this session was, in one paragraph, in my voice)_",
    "",
    "### His beats, verbatim",
    "",
    "_(unfilled - his rulings and asides as he said them, quoted not paraphrased)_",
    "",
    "### What I judged, and what I want next",
    "",
    "_(unfilled - the call the rows cannot make, and the want it leaves behind)_",
    "",
)

_AXIS_NOTE = (
    "The body is keyed BY AXIS, not fused into one stream — his fibre law at the close: "
    "*different results, different axes*. An item can sit on several axes; it is written out "
    "in full under the one axis named as its default section, and appears elsewhere as a "
    "cross-reference stating its role there. So a result that matters three ways is still one "
    "fact, counted once."
)


def render_dated(*, date: str, slug: str, slug_source: str, mark: str | None,
                 commits: dict[str, Any], bundle: dict[str, Any],
                 work_orders: dict[str, Any], promises: dict[str, Any],
                 threads: dict[str, Any], authored: list[str] | None = None) -> str:
    """The dated handoff, rendered. ``authored`` carries a previous pass's authored section
    forward verbatim; ``None`` means write the template."""
    mark_txt = mark or "no banked mark - the whole window is in scope"
    counts = " · ".join(f"{a} {len(bundle['by_axis'][a]['owned'])}"
                        f"(+{len(bundle['by_axis'][a]['cross'])} cross)" for a in AXES)
    authored_text = "\n".join(authored or []).strip()
    opening = []
    if authored_text and "_(unfilled" not in authored_text:
        opening = [sourced(
            f"**Authored checkpoint; publication recorded separately:** {_cap(authored_text, 600)}",
            "#the-authored-close-his-beats-the-voice"), ""]
    out: list[str] = [
        f"# SESSION HANDOFF — {date} — {slug.replace('-', ' ')}",
        "",
        *opening,
        "Rendered at the close by `scripts/sewup.py` step_handoff (`laplace.engine.handoff_render`) "
        "from the rows this session moved. Every line below carries the row that produced it "
        "in a trailing `[source]` span, so a reader descends to the row instead of trusting "
        "the summary. The authored section at the foot is the only written part, and the "
        "render never composes or overwrites it.",
        "",
        _AXIS_NOTE,
        "",
        sourced(f"- close mark: `{mark_txt}`", "close_beats.last_banked_close"),
        sourced(f"- session named from: `{slug_source}`", "the session's own naming doc"),
        sourced(f"- bundle: {len(bundle['items'])} item(s) — {counts}",
                "laplace.engine.handoff_render.axis_bundle"),
    ]
    if commits.get("error"):
        out.append(sourced(f"- spine unavailable: {commits['error']}", "git log"))
    elif commits.get("clipped"):
        out.append(sourced(f"- {commits['clipped']} older commit(s) clipped at the "
                           f"{MAX_COMMITS}-row cap, counted not dropped", "git log"))

    for axis in AXES:
        out += ["", f"## {AXIS_TITLE[axis]}", ""]
        out += _axis_lines(axis, bundle)

    out += ["", "## The obligations (not axis-keyed: these are debts, not results)", ""]
    out += [sourced(f"- work orders: {work_orders['total']} row(s) moved since the mark",
                    WORK_ORDERS)]
    out += _delta_lines(work_orders)
    out += [sourced(f"- promises: {promises['total']} row(s) moved since the mark", PROMISES)]
    out += _delta_lines(promises)

    out += ["", "## Thread probes (the scored rehearsal)", ""]
    out += _thread_lines(threads)

    out += ["", AUTHORED_HEADING]
    out += list(authored) if authored is not None else list(_AUTHORED_TEMPLATE)
    return "\n".join(out).rstrip("\n") + "\n"


def _axis_lines(axis: str, bundle: dict[str, Any]) -> list[str]:
    section = bundle["by_axis"][axis]
    lines: list[str] = []
    for it in section["owned"]:
        lines.append(sourced(f"- {it['label']}{it['extra']}", it["source"]))
    for it in section["cross"]:
        lines.append(sourced(
            f"- cross-ref → {_cap(_strip_marks(it['label']), LABEL_CAP)} — role here: "
            f"{it['axes'][axis]}; written out under **{it['default']}**", it["source"]))
    if not lines:
        lines.append(sourced("- nothing on this axis since the mark",
                             "laplace.engine.handoff_render.axis_bundle"))
    return lines


def _strip_marks(label: str) -> str:
    return label.replace("**", "")


def _delta_lines(delta: dict[str, Any]) -> list[str]:
    """One ledger's delta, bounded per class. A class that overflows says how many it is not
    printing and where they live — the clip is stated, so the count stays trustworthy."""
    rel = delta["rel"]
    lines: list[str] = []
    for cls in ("raised", "amended", "resolved", "deferred", "noted"):
        rows = delta["buckets"][cls]
        for row in rows[:LEDGER_SHOWN]:
            target = f" → {row['target']}" if row["target"] else ""
            # the EFFECTIVE status rides the line; a drift between it and the stored
            # raise-time field is stated in place (never hidden, never rewritten)
            eff = row.get("effective", row["status"])
            drift = (f" [{row['status']}→{eff} {row.get('status_reason', '')}]".rstrip()
                     if eff != row["status"] else (f" [{eff}]" if eff else ""))
            status = drift
            lines.append(sourced(
                f"  - {cls}: **{row['id']}**{target}{status} — {row['what']}",
                f"{rel}#{row['id']}"))
        if len(rows) > LEDGER_SHOWN:
            lines.append(sourced(
                f"  - {cls}: {len(rows) - LEDGER_SHOWN} further row(s) beyond the "
                f"{LEDGER_SHOWN}-row display cap, counted not dropped", rel))
    if not lines:
        lines.append(sourced("  - no row moved since the mark", rel))
    return lines


def _thread_lines(threads: dict[str, Any]) -> list[str]:
    if threads.get("error"):
        return [sourced(f"- {threads['error']}", THREAD_PROBES)]
    lines = [sourced(f"- scored at {threads.get('scored_at') or 'never'}: "
                     f"{threads['hit']}/{threads['scored']} probes reached their node",
                     f"{THREAD_PROBES}#last_scored")]
    for row in threads["rows"]:
        lines.append(sourced(
            f"- **{row['id']}**: banked `{row['expected']}` → scored "
            f"`{row['verdict'] or 'unscored'}` ({row['status']})",
            f"{THREAD_PROBES}#{row['id']}"))
    return lines


def _still_open(line: dict[str, str]) -> bool:
    """Is this rendered ledger line still live work? Reads ``effective`` (the joined
    status) when present, falling back to the stored field for a line minted before
    the join existed. An empty status is open by the raise-time convention."""
    status = line.get("effective", line.get("status", ""))
    return status in ("", "open")


def render_aim(*, date: str, slug: str, mark: str | None, dated: str,
               commits: dict[str, Any], bundle: dict[str, Any],
               predictions: list[dict[str, str]], work_orders: dict[str, Any],
               promises: dict[str, Any], threads: dict[str, Any],
               authored: list[str] | None = None,
               account_summary: dict[str, Any] | None = None) -> str:
    """Current authored result first, with its exact dated source, then bounded ledger context.

    The excerpt is carried from the session writer, not inferred from historical counts.
    The full authored text remains in the dated checkpoint when the excerpt is capped.
    """
    authored_text = "\n".join(authored or []).strip()
    result = (sourced(f"**Result and next action:** {_cap(authored_text, 1800)}",
                      f"{dated}#the-authored-close-his-beats-the-voice")
              if authored_text and "_(unfilled" not in authored_text else "Authored checkpoint is available in the dated record below.")
    account = account_summary or {}
    account_lines = []
    if "work_orders_open" in account:
        account_lines = [
            sourced(f"**Open account:** {account['work_orders_open']} work orders "
                    f"({account['work_orders_deferred']} deferred); {account['promises_open']} promises. "
                    f"Work-order examples: {_ids(account.get('work_orders_open_ids', []))}.",
                    "laplace.engine.wake.account_capped; scripts/laplace-python scripts/wake.py --account"),
            sourced(f"**Recorded red findings:** {account['thread_reds']}, last scored "
                    f"{account.get('thread_scored_at') or 'unknown'}: "
                    f"{_ids(account.get('thread_red_ids', []))}. These are recorded findings, not a fresh rerun.",
                    "laplace.engine.wake.account_capped; " + THREAD_PROBES), "",
        ]
    else:
        account_lines = ["**Open account:** unavailable; use `wake --account` for the observed fault.", ""]
    return "\n".join([
        f"{AIM_PREFIX} ({date}){LATEST_SUFFIX}", "", "<!-- laplace:authored-next:start -->", result, "<!-- laplace:authored-next:end -->", "",
        f"**Session record:** `{dated}`. Historical ledger details remain there.",
        "**Current publication and recovery:** `scripts/laplace-python scripts/wake.py --health`.",
        "**Programme:** reconstruct `ATLAS_DEVELOPMENT_STATE.md`; current operation is in `TECHNICAL_GUIDE.md`.", "",
        *account_lines,
    ])



# --------------------------------------------------------------------------- #
# the writes — one transaction, or neither
# --------------------------------------------------------------------------- #
def authored_block(text: str) -> list[str] | None:
    """The authored section of an existing dated file, verbatim, or None when it has none.

    This is what makes a re-render safe: the close can run twice in a night and the words
    written between the two runs survive, because the render carries them rather than
    regenerating around them.
    """
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if ln.strip() == AUTHORED_HEADING:
            return lines[i + 1:]
    return None


def aim_span(text: str) -> tuple[int, int]:
    """``[start, end)`` line span of the live agenda's newest block, or ``(-1, -1)``.

    The block runs from its heading to the next heading of any level, trailing blank line
    included, so excising the span restores the file exactly — the property a caller uses to
    prove the writer touched nothing else.
    """
    lines = text.split("\n")
    start = -1
    for i, ln in enumerate(lines):
        if ln.startswith(AIM_PREFIX) and ln.rstrip().endswith(LATEST_SUFFIX.strip()):
            start = i
            break
    if start < 0:
        return -1, -1
    end = start + 1
    while end < len(lines) and not _HEADING.match(lines[end]):
        end += 1
    return start, end


def splice_aim(text: str, block: str) -> str:
    """Replace the current agenda; retain the stable map without accumulating old agendas.

    Exact prior agendas remain in dated handoffs and git history. Accept the older arrow
    grammar and the current plain heading so either entry upgrades on its next close.
    """
    lines = text.split("\n")
    kept: list[str] = []
    index = 0
    anchor = None
    while index < len(lines):
        heading = lines[index]
        is_agenda = any(heading.startswith(prefix) for prefix in
                        (AIM_PREFIX, PRIOR_PREFIX, "## NEXT SESSION AIM", "## PRIOR AIM"))
        if is_agenda:
            if anchor is None:
                anchor = len(kept)
            index += 1
            while index < len(lines) and not lines[index].startswith(("# ", "## ")):
                index += 1
            continue
        kept.append(heading)
        index += 1
    if anchor is None:
        title = next((i for i, line in enumerate(kept) if line.startswith("# ")), -1)
        anchor = min(title + 2 if title >= 0 else 0, len(kept))
    return "\n".join(kept[:anchor] + block.rstrip().split("\n") + [""] + kept[anchor:])


def _checkpoint_path(root: Path, base: str, authored: str | None) -> Path:
    """Reuse the pointed current version, or preserve different authored text under its hash.

    A repeated identical close reuses its file. A different authored version is another normal
    dated handoff, not an archive copy; the previous record remains directly recoverable.
    """
    path = root / base
    if authored is None:
        try:
            live = (root / HANDOFF).read_text(encoding="utf-8")
            pattern = re.escape(Path(base).stem) + r"(?:-[0-9a-f]{16})?\.md"
            pointed = re.search(pattern, live)
            if pointed and (root / pointed.group(0)).is_file():
                return root / pointed.group(0)
        except OSError:
            pass  # the write path reports unreadable HANDOFF; dry-run may still preview
        return path
    if path.is_file():
        previous = "\n".join(authored_block(path.read_text(encoding="utf-8")) or []).strip()
        if previous and "_(unfilled" not in previous and previous != authored.strip():
            suffix = hashlib.sha256(authored.strip().encode("utf-8")).hexdigest()[:16]
            path = root / f"{Path(base).stem}-{suffix}.md"
            if path.is_file():
                stored = "\n".join(authored_block(path.read_text(encoding="utf-8")) or []).strip()
                if stored != authored.strip():
                    raise ValueError(f"authored checkpoint identity collision: {path.name}")
    return path


def _stage_bytes(target: Path, data: bytes) -> Path:
    """Write a complete same-directory replacement before touching its destination."""
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if target.exists():
                os.fchmod(stream.fileno(), target.stat().st_mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def render_close(repo_root: Path | str, *, date: str | None = None, slug: str | None = None,
                 since: str | Any = ..., dry_run: bool = False,
                 scratch: Path | str | None = None, authored: str | None = None) -> dict[str, Any]:
    """Collect the rows, bundle them by axis, render the pair, write it as one transaction.

    ``authored`` supplies the session writer's text; otherwise an existing authored section
    is carried verbatim, or a visible template is written for the caller to complete.
    ``since=...`` resolves the close mark; pass a value (or None for "the whole window") to
    override. ``dry_run=True`` renders both halves, drops copies under ``scratch`` outside the
    repo, and leaves the repo untouched — the rendered text comes back in the result either
    way, which is what makes the dry run a real preview rather than a rehearsal of one.
    """
    root = Path(repo_root)
    mark = close_mark(root) if since is ... else since
    date = date or time.strftime("%Y-%m-%d")
    slug_source = "caller-supplied"
    if slug is None:
        slug, slug_source = session_slug(root, since=mark, date=date)

    commits = commits_since(root, mark)
    predictions = prediction_rows(root, mark)
    docs = session_docs(root, since=mark, date=date)
    rulings = ruling_rows(root, mark)
    work_orders = ledger_delta(root, WORK_ORDERS, mark)
    promises = ledger_delta(root, PROMISES, mark)
    threads = thread_delta(root)
    bundle = axis_bundle(commits=commits, predictions=predictions, docs=docs, rulings=rulings)

    dated_path = _checkpoint_path(root, dated_name(date, slug), authored)
    dated_rel = dated_path.name
    existed = dated_path.is_file()
    carried = authored.strip().splitlines() if authored is not None else None
    if existed and authored is None:
        try:
            carried = authored_block(dated_path.read_text(encoding="utf-8"))
        except OSError:
            carried = None

    dated_text = render_dated(date=date, slug=slug, slug_source=slug_source, mark=mark,
                              commits=commits, bundle=bundle, work_orders=work_orders,
                              promises=promises, threads=threads, authored=carried)
    from laplace.engine.wake import account_capped
    account_summary = account_capped(root, ids_cap=4)
    aim_text = render_aim(date=date, slug=slug, mark=mark, dated=dated_rel, commits=commits,
                          bundle=bundle, predictions=predictions, work_orders=work_orders,
                          promises=promises, threads=threads, authored=carried, account_summary=account_summary)

    res: dict[str, Any] = {
        "ok": True, "error": None, "mark": mark, "date": date, "slug": slug,
        "slug_source": slug_source, "dated": dated_rel, "dated_existed": existed,
        "authored_carried": existed and authored is None and carried is not None,
        "authored_supplied": authored is not None,
        "axes": {a: {"owned": len(bundle["by_axis"][a]["owned"]),
                     "cross": len(bundle["by_axis"][a]["cross"])} for a in AXES},
        "counts": {"commits": len(commits.get("rows") or []),
                   "commits_clipped": commits.get("clipped", 0),
                   "items": len(bundle["items"]),
                   "predictions": len(predictions), "docs": len(docs),
                   "rulings": len(rulings),
                   "work_orders": work_orders["total"], "promises": promises["total"],
                   "threads_scored": threads.get("scored", 0),
                   "threads_hit": threads.get("hit", 0)},
        "spine_error": commits.get("error"),
        "threads_error": threads.get("error"),
        "dated_text": dated_text, "aim_text": aim_text,
        "unsourced": check_sourced(dated_text) + check_sourced(aim_text),
        "dry_run": dry_run, "written": [], "scratch": None,
    }

    if dry_run:
        base = Path(scratch) if scratch else Path(tempfile.gettempdir()) / "laplace-close-render"
        try:
            base.mkdir(parents=True, exist_ok=True)
            (base / dated_rel).write_text(dated_text, encoding="utf-8")
            (base / f"{HANDOFF}.aim").write_text(aim_text, encoding="utf-8")
            res["scratch"] = str(base)
        except OSError as exc:
            res["scratch"] = f"scratch unwritable: {exc}"
        return res

    live_path = root / HANDOFF
    try:
        live_before = live_path.read_text(encoding="utf-8")
    except OSError as exc:
        res.update(ok=False, error=f"{HANDOFF} unreadable ({exc}) - refusing to write the "
                                   f"dated file and leave the live agenda stale")
        return res
    dated_before = dated_path.read_bytes() if existed else None
    dated_stat = dated_path.stat() if existed else None
    staged: list[Path] = []
    installed = False
    try:
        dated_tmp = _stage_bytes(dated_path, dated_text.encode("utf-8"))
        staged.append(dated_tmp)
        live_tmp = _stage_bytes(live_path, splice_aim(live_before, aim_text).encode("utf-8"))
        staged.append(live_tmp)
        dated_tmp.replace(dated_path)
        installed = True
        live_tmp.replace(live_path)
    except OSError as exc:
        rolled = not installed
        if installed:
            try:
                if dated_before is None:
                    dated_path.unlink()
                else:
                    rollback = _stage_bytes(dated_path, dated_before)
                    staged.append(rollback)
                    rollback.replace(dated_path)
                    os.utime(dated_path, ns=(dated_stat.st_atime_ns, dated_stat.st_mtime_ns))
                rolled = True
            except OSError:
                rolled = False
        res.update(ok=False, error=f"checkpoint pair unwritable: {exc}"
                   + (f" - {dated_rel} rolled back" if rolled
                      else f" - {dated_rel} is on disk and the pair is split"))
        return res
    finally:
        for temporary in staged:
            temporary.unlink(missing_ok=True)
    res["written"] = [dated_rel, HANDOFF]
    return res


def report_lines(res: dict[str, Any]) -> list[str]:
    """The loud half: what was rendered, from how many rows of what, and where it went."""
    c = res.get("counts", {})
    mark = res.get("mark") or "no close mark - the whole window was in scope"
    out = [f"rendered {res.get('dated')} from rows since {mark}"
           + (" (dry run, nothing written in-repo)" if res.get("dry_run") else "")]
    out.append(f"spine {c.get('commits', 0)} commit(s)"
               + (f" (+{c['commits_clipped']} clipped)" if c.get("commits_clipped") else "")
               + f" | {c.get('predictions', 0)} prediction row(s)"
               + f" | {c.get('docs', 0)} session doc(s)"
               + f" | {c.get('rulings', 0)} ruling row(s)"
               + f" | {c.get('work_orders', 0)} work-order row(s)"
               + f" | {c.get('promises', 0)} promise row(s)"
               + f" | threads {c.get('threads_hit', 0)}/{c.get('threads_scored', 0)}")
    axes = res.get("axes") or {}
    out.append("axes: " + " · ".join(f"{a} {axes.get(a, {}).get('owned', 0)}"
                                     f"(+{axes.get(a, {}).get('cross', 0)} cross)"
                                     for a in AXES))
    out.append(f"named from {res.get('slug_source')}")
    if res.get("authored_supplied"):
        out.append("preserved the supplied authored checkpoint")
    elif res.get("authored_carried"):
        out.append("carried the existing authored section forward verbatim")
    elif not res.get("dry_run"):
        out.append("authored slot left as a template - the close's dialogue beats fill it")
    if res.get("spine_error"):
        out.append(f"spine: {res['spine_error']}")
    if res.get("threads_error"):
        out.append(f"threads: {res['threads_error']}")
    if res.get("unsourced"):
        out.append(f"UNSOURCED lines ({len(res['unsourced'])}): "
                   + " / ".join(ln.strip()[:60] for ln in res["unsourced"][:3]))
    if res.get("scratch"):
        out.append(f"scratch render: {res['scratch']}")
    for rel in res.get("written") or []:
        out.append(f"wrote {rel}")
    if res.get("error"):
        out.append(f"ERROR: {res['error']}")
    return out
