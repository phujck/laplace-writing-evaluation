"""Audit every dispatch model stamp against the dispatch-model law, two-sided.

THE CEILING (his law, 2026-07-11): Eigen orchestrates; dispatched agents are
OPUS-LEVEL OR LESS. The python side is carried by ``pipeline.dispatch.compile_dispatch``
(stamps model/effort, clamped to ``schema.MAX_MODEL``). But the REAL dispatch sites
the compiler cannot reach are the ``model: 'sonnet'`` literals in the .mjs/.js workflow
scripts, consumed by the harness-provided ``agent()`` runner outside this repo. This
audit is the enforcement that reaches them: scan every workflow file, extract every
model literal, fail loudly on any token above the ceiling (or unknown - unknown is
never silently allowed).

The source audit reads contract/dispatches.jsonl and legacy codex-dispatch records in
corpus_friction/**/*.jsonl. Their packet_model_stamp obeys the same ceiling; executor,
codex_model and sandbox must be explicit. Codex model ids are transport metadata, not
Claude tier tokens. Row counts name each surface separately, including zero rows.

THE FLOOR (B17, 2026-08-04) is the conjugate, and it answers a different question: not
"did a stage run too rich" but "did every stage of a MEASURED ARM actually run at the
tier the arm claims". A benchmark whose claim is the engine rather than the model is
only honest if no stage rode a cheaper model, so ``--floor <tier>`` makes a token below
the required tier a violation too. Off by default: the ceiling is the standing law, the
floor is a per-arm demand.

TWO INPUT CLASSES. Source (the default) proves the POLICY - what the scripts are
written to dispatch. ``--run <dir>`` proves the RUN - what a completed run actually
stamped, read from the per-stage manifests the organs already bank
(``agents_manifest.json`` from .claude/workflows/project-harnessed.js, and
``dispatch_manifest.json`` from the loop runners). A policy audit alone cannot show a
run obeyed it; a run audit alone cannot show the next run will.

THE ONE EXEMPTION, BY LABEL. Every organ's first agent is the ``load-dials`` bootstrap
at a hardcoded haiku - it is the stage that FETCHES the dials, so it structurally cannot
read the tier it should run at. It is exempt from the FLOOR only (never from the
ceiling), matched by LABEL so the exemption is one named stage and cannot silently
widen, and emitted as an explicit row in the output so it is disclosed rather than
invisible.

Run:  python3 scripts/audit_dispatch_models.py [--root PATH] [--floor TIER] [--run PATH]
Exit: 0 = every stamp within the law; 1 = violation(s), each printed with file:locus.
The suite runs this via tests/test_dispatch_model_ceiling.py and
tests/test_model_floor_audit.py, so a violation is a red bar.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.pipeline.schema import MAX_MODEL, MODEL_RANK  # noqa: E402

#: where hand-written dispatch literals live (the compiler-unreachable sites).
#:
#: The globs are RECURSIVE (B17). They were ``scripts/*.mjs``-shaped until 2026-08-04,
#: and that non-recursion was a false green: four real dispatch sites sat one directory
#: down and were never scanned (scripts/workflows/, workflows/, experiments/). A check
#: an author can evade by making a subdirectory is not a check.
#:
#: ``src/atlas/tools/raptor_fold.py`` joined this list in Phase 3. It is the atlas
#: bench's RAPTOR summarizer, and it shells out to a dispatched agent once per batch with
#: an explicit ``"model": "<token>"`` literal in exactly the shape ``_LITERAL`` matches. A
#: dispatch site the auditor cannot see is the hole the auditor exists to close, so the
#: site was added here rather than merely written to comply. The audit reads the file as
#: TEXT and imports nothing from it - the atlas seal is untouched in both directions.
SCAN_GLOBS = ("scripts/**/*.mjs", "scripts/**/*.js",
              ".claude/workflows/**/*.mjs", ".claude/workflows/**/*.js",
              "workflows/**/*.mjs", "workflows/**/*.js",
              "experiments/**/*.mjs", "experiments/**/*.js",
              "src/atlas/tools/raptor_fold.py")

#: vendored / installed trees are never dispatch sites of ours. The narrow globs
#: avoided these incidentally; recursion has to refuse them on purpose.
SKIP_PARTS = {".venv", "venv", "node_modules", ".git", "site-packages", "__pycache__"}

#: the per-run stamp banks the organs already write, relative to a --run root.
RUN_GLOBS = ("**/agents_manifest.json", "**/dispatch_manifest.json")

#: model: 'x' / model: "x" / "model": "x"  (the shapes the agent() runner consumes)
_LITERAL = re.compile(r"""["']?model["']?\s*:\s*["']([\w.-]+)["']""")

#: the bootstrap constant the organs name their load-dials tier with. It is an
#: IDENTIFIER at the dispatch site (`model: BOOTSTRAP_MODEL`), so _LITERAL cannot see
#: it; without this pattern the one stage the floor most needs to account for would be
#: the one stage invisible to it.
_BOOTSTRAP = re.compile(r"""BOOTSTRAP_MODEL\s*=\s*["']([\w.-]+)["']""")

#: stage labels exempt from the FLOOR (never from the ceiling). Exactly one member,
#: and the audit prints a row for every match so the exemption is disclosed.
FLOOR_EXEMPT_LABELS = frozenset({"load-dials"})

#: ``contract/dispatches.jsonl`` is the dispatch EVENT ledger, and a dispatch row is not the
#: only kind of event in it: ``laplace.pipeline.workflow`` banks ``workflow`` and
#: ``workflow-stage`` rows there, and so does ``scripts/distil.py wave-rows``. Those rows
#: record a run, not a packet, and carry no model to stamp - auditing them as malformed
#: dispatch rows is the gate firing on the wrong cause (the 2026-09-15 lesson recorded in
#: ``_dispatch_rows`` below). The corpus surface already applies exactly this rule, skipping
#: any record that is not ``codex-dispatch``, and ``tests/test_dispatch_model_ceiling.py``
#: asserts it there; this is the same rule on the ledger surface. A record kind that is NOT
#: named here - including a missing or misspelled ``record`` - stays a violation, so a row
#: that should have been audited cannot hide behind the skip.
LEDGER_EVENT_RECORDS = frozenset({"workflow", "workflow-stage"})

_EXEMPT_WHY = "bootstrap: the stage that fetches the dials cannot read them first"


class Row(NamedTuple):
    """One model stamp. ``locus`` is a 1-based LINE for a source file and the stage
    ordinal (or row index) for a run manifest - the coordinate that locates the stamp
    in the artefact it came from. ``label`` is '' when the site names no stage."""
    path: Path
    locus: int
    token: str
    label: str = ""
    kind: str = "source"


class Report(NamedTuple):
    violations: list[Row]
    exemptions: list[Row]
    files: int
    dispatch_rows: int = 0
    corpus_rows: int = 0


def tier_of(token: str) -> str | None:
    """The MODEL_RANK tier a stamp names, or ``None`` if it names none.

    A bare tier token is itself. A versioned provider id (``claude-opus-5``,
    ``us.anthropic.claude-sonnet-4-5-20250929``) resolves to the tier it contains -
    run ledgers record exact ids, and an id the audit cannot read is an id it cannot
    enforce. The provider component is REQUIRED for that resolution: ``opus-max`` is
    not an id, it is an unknown token, and unknown is never silently allowed."""
    if token in MODEL_RANK:
        return token
    parts = re.split(r"[-._]", token)
    if "claude" not in parts:
        return None
    tiers = [p for p in parts if p in MODEL_RANK]
    return tiers[0] if len(tiers) == 1 else None


def _verdict(row: Row, ceiling: int, floor: int | None) -> str:
    """``'ok'`` | ``'violation'`` | ``'exempt'`` for one stamp."""
    rank = {m: i for i, m in enumerate(MODEL_RANK)}
    tier = tier_of(row.token)
    if tier is None or rank[tier] > ceiling:
        return "violation"
    if floor is None or rank[tier] >= floor:
        return "ok"
    if row.label in FLOOR_EXEMPT_LABELS:
        return "exempt"
    return "violation"


def _source_rows(root: Path) -> tuple[list[Row], int]:
    rows: list[Row] = []
    files = 0
    for f in _iter_files(root):
        files += 1
        for lineno, line in enumerate(f.read_text(encoding="utf-8",
                                                  errors="replace").splitlines(), 1):
            for m in _LITERAL.finditer(line):
                rows.append(Row(f, lineno, m.group(1)))
            for m in _BOOTSTRAP.finditer(line):
                rows.append(Row(f, lineno, m.group(1), "load-dials"))
    return rows, files


def _manifest_rows(path: Path, blob: Any, rows: list[Row], idx: list[int]) -> None:
    """Walk a run manifest for every mapping carrying a ``model``. The shape differs
    per organ (a flat list of stage records; a nested waves list), so the walk is
    structural rather than per-schema - a new manifest shape is covered on arrival."""
    if isinstance(blob, dict):
        model = blob.get("model")
        if isinstance(model, str) and model:
            ordinal = blob.get("ordinal")
            label = blob.get("label") or blob.get("worker") or ""
            rows.append(Row(path, ordinal if isinstance(ordinal, int) else idx[0],
                            model, str(label), "run"))
            idx[0] += 1
        for v in blob.values():
            _manifest_rows(path, v, rows, idx)
    elif isinstance(blob, list):
        for v in blob:
            _manifest_rows(path, v, rows, idx)


def _run_rows(run_root: Path) -> tuple[list[Row], int]:
    rows: list[Row] = []
    files = 0
    for f in _iter_run_files(run_root):
        files += 1
        try:
            blob = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            # an unreadable manifest is not a clean run: it is a run whose stamps
            # cannot be proven, and silence there is the failure mode this exists for.
            rows.append(Row(f, 0, "<unparseable manifest>", "", "run"))
            continue
        _manifest_rows(f, blob, rows, [0])
    return rows, files


def _dispatch_rows(root: Path) -> tuple[list[Row], int, int]:
    rows: list[Row] = []
    dispatch_count = corpus_count = 0

    def append(path: Path, locus: int, blob: Any) -> None:
        if not isinstance(blob, dict):
            rows.append(Row(path, locus, "<malformed dispatch row>", kind="dispatch"))
            return
        # A REFUSED dispatch never compiled a packet, so it has no model to stamp and nothing ran
        # at any tier. Auditing it as a ceiling violation is the gate firing on the wrong cause
        # (2026-09-15: the ledger's refused row for an over-budget reconstruction turned the floor
        # red, and the model law was never in question). The refusal itself is the record.
        if str(blob.get("status") or "").upper() == "REFUSED":
            return
        for field in ("executor", "codex_model", "sandbox"):
            value = blob.get(field)
            if not isinstance(value, str) or not value.strip():
                rows.append(Row(path, locus, f"<missing {field}>", kind="dispatch"))
        model = blob.get("packet_model_stamp")
        token = model if isinstance(model, str) and model else "<missing packet_model_stamp>"
        rows.append(Row(path, locus, token, kind="dispatch"))

    path = root / "contract/dispatches.jsonl"
    if path.is_file():
        try:
            with path.open(encoding="utf-8") as stream:
                for locus, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    dispatch_count += 1
                    try:
                        blob = json.loads(line)
                    except json.JSONDecodeError:
                        rows.append(Row(path, locus, "<unparseable dispatch row>", kind="dispatch"))
                        continue
                    if isinstance(blob, dict) and blob.get("record") in LEDGER_EVENT_RECORDS:
                        continue
                    if not isinstance(blob, dict) or blob.get("record") != "dispatch":
                        rows.append(Row(path, locus, "<malformed dispatch row>", kind="dispatch"))
                        continue
                    append(path, locus, blob)
        except (OSError, UnicodeError):
            rows.append(Row(path, 0, "<unreadable dispatch ledger>", kind="dispatch"))
    for path in sorted((root / "corpus_friction").rglob("*.jsonl")):
        try:
            with path.open(encoding="utf-8") as stream:
                for locus, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        blob = json.loads(line)
                    except json.JSONDecodeError:
                        rows.append(Row(path, locus, "<unparseable corpus row>", kind="dispatch"))
                        continue
                    if isinstance(blob, dict) and blob.get("record") == "codex-dispatch":
                        corpus_count += 1
                        append(path, locus, blob)
        except (OSError, UnicodeError):
            rows.append(Row(path, 0, "<unreadable corpus ledger>", kind="dispatch"))
    return rows, dispatch_count, corpus_count


def scan(root: Path, floor: str | None = None, run: Path | None = None) -> Report:
    """Every stamp in scope, sorted into violations and disclosed exemptions."""
    rank = {m: i for i, m in enumerate(MODEL_RANK)}
    if floor is not None and floor not in rank:
        raise ValueError(f"unknown floor tier {floor!r}; one of {MODEL_RANK}")
    ceiling = rank[MAX_MODEL]
    floor_rank = rank[floor] if floor is not None else None
    rows, files = _run_rows(run) if run is not None else _source_rows(root)
    dispatch_count = corpus_count = 0
    if run is None:
        dispatch_rows, dispatch_count, corpus_count = _dispatch_rows(root)
        rows.extend(dispatch_rows)
    violations = [r for r in rows if _verdict(r, ceiling, floor_rank) == "violation"]
    exemptions = [r for r in rows if _verdict(r, ceiling, floor_rank) == "exempt"]
    return Report(violations, exemptions, files, dispatch_count, corpus_count)


def audit(root: Path, floor: str | None = None,
          run: Path | None = None) -> list[Row]:
    """Return violations as (file, locus, token, label, kind) rows."""
    return scan(root, floor=floor, run=run).violations


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--floor", default=None,
                    help=f"required MINIMUM tier ({'|'.join(MODEL_RANK)}); "
                         "off by default - the ceiling is the standing law")
    ap.add_argument("--run", type=Path, default=None,
                    help="audit a RUN: the per-stage manifests under this directory "
                         "instead of the source dispatch sites")
    a = ap.parse_args(argv)
    rep = scan(a.root, floor=a.floor, run=a.run)
    base = a.run if a.run is not None else a.root
    if a.run is None:
        print(f"dispatch row surface: {rep.dispatch_rows} contract/dispatches.jsonl event rows; "
              f"{rep.corpus_rows} corpus_friction codex-dispatch rows scanned")
    for r in rep.exemptions:
        print(f"  EXEMPT(floor) {_rel(r.path, base)}:{r.locus}: label "
              f"{r.label!r} model {r.token!r} - {_EXEMPT_WHY}")
    if rep.violations:
        law = f"ceiling {MAX_MODEL}" + (f", floor {a.floor}" if a.floor else "")
        print(f"DISPATCH-MODEL LAW VIOLATED ({len(rep.violations)}; {law})")
        for r in rep.violations:
            lbl = f" label {r.label!r}" if r.label else ""
            print(f"  {_rel(r.path, base)}:{r.locus}:{lbl} model {r.token!r}")
        return 1
    what = "run manifests" if a.run is not None else "workflow files"
    law = f"ceiling {MAX_MODEL}" + (f"; floor {a.floor}" if a.floor else "")
    print(f"dispatch-model audit: OK ({law}; {rep.files} {what} scanned; "
          f"{len(rep.exemptions)} exempt)")
    return 0


def _rel(p: Path, base: Path) -> str:
    try:
        return str(p.relative_to(base))
    except ValueError:
        return str(p)


def _iter_files(root: Path):
    seen: set[Path] = set()
    for pattern in SCAN_GLOBS:
        for f in sorted(root.glob(pattern)):
            if SKIP_PARTS & set(f.parts) or f in seen or not f.is_file():
                continue
            seen.add(f)
            yield f


def _iter_run_files(run_root: Path):
    if run_root.is_file():
        yield run_root
        return
    seen: set[Path] = set()
    for pattern in RUN_GLOBS:
        for f in sorted(run_root.glob(pattern)):
            if SKIP_PARTS & set(f.parts) or f in seen or not f.is_file():
                continue
            seen.add(f)
            yield f


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
