"""The reader-verdict TRANSPORT shim — the CLEAN/LABEL bit travels by FILE + EXIT CODE.

Banked lesson (the weak seam this closes): *every model-in-the-middle is a lossy
channel.* At candidate-lock each sealed/referee/vision reader used to PARSE its own
reply and then hand the loop a free-form ``return {label, clean, findings_n}`` as
agent JSON — the CLEAN/LABEL verdict rode a model. This module makes that bit
DETERMINISTIC and on-disk: a reader's one verbatim command ends by piping its raw
reply through the ``write`` CLI here, which

  * calls the reader's OWN pure parse organ (``sealed.parse_sealed_verdict`` /
    ``referee.parse_referee_verdict`` / ``visual.parse_figure_verdict`` /
    ``visual.parse_geometry_verdict``) — the parse organs stay pure, this is only
    the shim that calls them,
  * writes ``<manuscript>/rounds/lock_r<N>/<rid>_verdict.json`` =
    ``{label, clean, findings_n, finding_ids}``,
  * EXITS NONZERO when ``clean`` is false (0 when clean) — clean/unclean is now a
    file plus an exit code, never an agent's paraphrase.

The label is taken from the roster (``READERS[rid].panel_label``) — even the LABEL
bit is single-sourced from the declarative spine, not the model. The agent's textual
return becomes telemetry only.

The ``assemble`` CLI rebuilds the per-round lock sidecar (``lock_r<N>.json``, the
list of panel entries the NEXT mechround merges) FROM the on-disk verdict files —
ONE source of truth. A rostered reader whose file is ABSENT becomes
``{label, failed: true}`` (silence never reads as pass); the ``calc`` mirror is
derived from the file-backed ``referee`` entry; the voice leg (a dominance decision,
not a findings verdict) is passed in as an extra entry.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from laplace.pipeline.readers.roster import READERS
from laplace.pipeline.ledger import finding_id as _ledger_finding_id


# ---------------------------------------------------------------------------
# Parser dispatch — the shim CALLS the pure organs, never reimplements them
# ---------------------------------------------------------------------------

def _reply_carries_json_list(raw: str) -> bool:
    """Whether the raw reply contains ANY complete JSON list or object — the
    minimum for 'the reader actually answered'. The organs tolerate prose-
    wrapped and fenced JSON, so this scans for a balanced JSON value anywhere;
    an empty/truncated/corrupt reply carries none and must read as FAILED,
    never as clean (the present-but-garbage leg of 'silence never passes')."""
    s = raw.strip()
    if not s:
        return False
    dec = json.JSONDecoder()
    for m in re.finditer(r"[\[{]", s):
        try:
            obj, _ = dec.raw_decode(s[m.start():])
        except ValueError:
            continue
        if isinstance(obj, (list, dict)):
            return True
    return False


def parse_reply(organ: str, rid: str, raw: str, strict: bool = False
                ) -> list[dict[str, Any]]:
    """Dispatch the raw reader reply to its OWN pure parse organ and return findings
    in the standard reader shape. ``organ`` selects the parser; the parse organs are
    untouched (this module only imports and calls them). Malformed input → ``[]`` by
    each tolerant organ's own tolerance. THE EXCEPTION is ``restart``/``r10``: its
    organ is fail-LOUD by design (C5.1a — a wrong-shape comparison RAISES rather than
    silently certifying clean); the write layer (``_cli_write``) catches the raise and
    banks a FAILED verdict file, so the crash is a first-class failed verdict."""
    if organ == "sealed":
        from laplace.pipeline.readers.sealed import parse_sealed_verdict
        return parse_sealed_verdict(rid, raw, strict=strict)
    if organ == "referee":
        from laplace.pipeline.readers.referee import parse_referee_verdict
        return parse_referee_verdict(raw, strict=strict)
    if organ == "figure":
        from laplace.pipeline.readers.visual import parse_figure_verdict
        return parse_figure_verdict(raw, strict=strict)
    if organ == "geometry":
        from laplace.pipeline.readers.visual import parse_geometry_verdict
        return parse_geometry_verdict(raw, strict=strict)
    if organ == "caption_blind":
        from laplace.pipeline.readers.caption_blind import parse_caption_blind_verdict
        return parse_caption_blind_verdict(raw, strict=strict)
    if organ in ("restart", "r10"):
        # R10 is a TWO-PHASE read, but the transport carries ONE reply: this organ
        # parses ONLY the COMPARE-phase reply — ``clean = no mismatches``. The blind
        # packet is banked separately (``restart_reader.bank``) and never rides
        # ``parse_reply``. Compose the reader's OWN pure organ (``make_reader_report``
        # owns the mismatch→finding verb law); the shim only calls it, as with the rest.
        from laplace.pipeline.readers.sealed import _coerce_json
        from laplace.pipeline.readers.restart_reader import make_reader_report
        return make_reader_report(None, _coerce_json(raw))["findings"]
    raise KeyError(f"{organ!r} is not a reader organ "
                   "(have sealed|referee|figure|geometry|caption_blind|restart)")


# ---------------------------------------------------------------------------
# Finding ids — carry a fingerprint/id if the finding exposes one, else derive
# ---------------------------------------------------------------------------

def _finding_id(f: dict[str, Any]) -> str:
    """A stable id for one finding — delegated to :func:`ledger.finding_id`, the
    SINGLE derivation the engine shares, so a finding's id is the same whether it is
    stamped here (the verdict-file transport), repaired at the live-view boundary, or
    assigned by the reader pour. Same ``content_fingerprint`` the suppression ledger
    uses; single-sourcing it is what lets an anchored re-pour supersede a legacy
    id-less original by the id both sides compute."""
    return _ledger_finding_id(f)


def _label_for(rid: str, label: Optional[str] = None) -> str:
    """The panel label for a reader — single-sourced from the roster's
    ``panel_label`` (not the model). A passed ``label`` is honoured only as a
    fallback when ``rid`` is not a rostered reader."""
    r = READERS.get(rid)
    return r.panel_label if r else (label or rid)


# ---------------------------------------------------------------------------
# 1. write_verdict — the per-reader verdict FILE (the CLEAN/LABEL transport)
# ---------------------------------------------------------------------------

def build_verdict(rid: str, label: Optional[str],
                  verdict: list[dict[str, Any]]) -> dict[str, Any]:
    """The verdict record for one reader: ``{label, clean, findings_n, finding_ids}``.
    ``verdict`` is the reader's PARSED findings list; ``clean`` is exactly
    ``len(verdict) == 0`` (deterministic — no agent claim). The label comes from the
    roster."""
    findings = list(verdict or [])
    return {
        "label": _label_for(rid, label),
        "reader": rid,
        "clean": len(findings) == 0,
        "findings_n": len(findings),
        "finding_ids": [_finding_id(f) for f in findings if isinstance(f, dict)],
    }


def write_verdict(rid: str, label: Optional[str], verdict: list[dict[str, Any]],
                  out_dir: "str | Path") -> dict[str, Any]:
    """Write ``<out_dir>/<rid>_verdict.json`` = ``{label, clean, findings_n,
    finding_ids}`` and return the record. ``out_dir`` is the lock-round directory
    (``<manuscript>/rounds/lock_r<N>``), created if absent. The parse organ that
    produced ``verdict`` stays pure — this is the transport."""
    rec = build_verdict(rid, label, verdict)
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{rid}_verdict.json").write_text(
        json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return rec


# ---------------------------------------------------------------------------
# 2. assemble_sidecar — the per-round sidecar, rebuilt FROM the on-disk files
# ---------------------------------------------------------------------------

def read_verdict(round_dir: "str | Path", rid: str) -> Optional[dict[str, Any]]:
    """Load one reader's on-disk verdict, or ``None`` if the file is absent/corrupt
    (absent → the reader did not report; the caller turns that into ``failed``)."""
    p = Path(round_dir) / f"{rid}_verdict.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (ValueError, OSError):
        return None


def _panel_entry(rid: str, data: Optional[dict[str, Any]]) -> dict[str, Any]:
    """One panel entry (``{label, clean, flags}``) from a file-backed verdict — or
    ``{label, failed: true}`` when the file is ABSENT for a rostered reader. Silence
    never reads as pass: an absent verdict is a failed reader, never a clean one.
    ``flags`` mirrors the prior sidecar shape (``[{n: findings_n}]`` when non-clean)
    so convergence scoring is unchanged."""
    if data is None:
        return {"label": _label_for(rid), "clean": False, "flags": [], "failed": True}
    n = int(data.get("findings_n") or 0)
    return {"label": data.get("label") or _label_for(rid),
            "clean": bool(data.get("clean")),
            "flags": [{"n": n}] if n else []}


def assemble_sidecar(round_dir: "str | Path", rostered: list[str],
                     extra_entries: Optional[list[dict[str, Any]]] = None,
                     calc_mirror: bool = True) -> list[dict[str, Any]]:
    """Rebuild the per-round lock panel-entry list FROM the on-disk per-reader
    verdict files — ONE source of truth. For each rostered reader: file present →
    entry from the FILE; file absent → ``{label, failed: true}``. The ``calc`` mirror
    is derived from the file-backed ``referee`` entry (the retired detail-sufficiency
    axis R2 owns). ``extra_entries`` (e.g. the voice leg's dominance verdict, which is
    not a findings reader) are appended verbatim."""
    entries: list[dict[str, Any]] = []
    for rid in rostered:
        entries.append(_panel_entry(rid, read_verdict(round_dir, rid)))
    if calc_mirror:
        ref = next((e for e in entries if e.get("label") == "referee"
                    and not e.get("failed")), None)
        if ref is not None:
            entries.append({"label": "calc", "clean": bool(ref.get("clean")),
                            "flags": list(ref.get("flags") or [])})
    for e in (extra_entries or []):
        if isinstance(e, dict) and e.get("label"):
            entries.append(e)
    return entries


# ---------------------------------------------------------------------------
# CLI — the verbatim tail of a reader's one command; and the sidecar assembler
# ---------------------------------------------------------------------------

def _cli_write(argv: list[str]) -> int:
    """``write <organ> <rid> <label> <out_dir>`` — read the raw reply from stdin,
    parse it with the reader's pure organ, write the verdict file, EXIT NONZERO iff
    unclean. The agent's own textual return is telemetry only; this file + exit code
    is the verdict."""
    if len(argv) < 4:
        sys.stderr.write("usage: verdict_io write <organ> <rid> <label> <out_dir>\n")
        return 2
    organ, rid, label, out_dir = argv[0], argv[1], argv[2], argv[3]
    raw = sys.stdin.read()
    # A present-but-garbage reply must NOT read as clean: the tolerant organs
    # return [] on a truncated/empty/corrupt reply, which is indistinguishable
    # from a genuine "no findings". Validate the raw reply carries a JSON list
    # somewhere (the organs accept prose-wrapped and fenced JSON); if none does,
    # bank a FAILED verdict and exit nonzero — corruption is loud, like absence.
    if not _reply_carries_json_list(raw):
        rec = {"rid": rid, "label": _label_for(rid, label), "clean": False,
               "failed": True, "findings_n": 0, "finding_ids": [],
               "note": "reply empty/unparseable — reader FAILED, not clean"}
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{rid}_verdict.json").write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        sys.stderr.write(f"verdict_io: {rid} reply empty/unparseable — FAILED\n")
        return 1
    # A fail-loud organ (restart: wrong-shape raises, C5.1a) must still bank a
    # verdict FILE — a raw traceback with no file is fail-closed only through
    # assemble's absent-file=failed rule, which is fragile. Catch, bank FAILED,
    # exit nonzero: the crash becomes a first-class failed verdict.
    try:
        findings = parse_reply(organ, rid, raw)
    except (ValueError, KeyError) as exc:
        rec = {"rid": rid, "label": _label_for(rid, label), "clean": False,
               "failed": True, "findings_n": 0, "finding_ids": [],
               "note": f"reply rejected by the {organ} organ — reader FAILED, "
                       f"not clean: {exc}"}
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{rid}_verdict.json").write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")
        sys.stderr.write(f"verdict_io: {rid} reply rejected ({exc}) — FAILED\n")
        return 1
    rec = write_verdict(rid, label, findings, out_dir)
    # telemetry to stdout; the loop reads the FILE, not this line.
    sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return 0 if rec["clean"] else 1


def _cli_assemble(argv: list[str]) -> int:
    """``assemble <round_dir> <sidecar_path> <rostered_csv>`` — rebuild the sidecar
    list from the on-disk verdict files and write it to ``<sidecar_path>`` (the list
    the next mechround merges). Extra panel entries (e.g. the voice leg's dominance
    verdict, which is not a findings reader) are read as a JSON list from STDIN — a
    heredoc, so JSON quotes never fight shell quoting; empty/``[]`` stdin is fine.
    Exit 0."""
    if len(argv) < 3:
        sys.stderr.write("usage: verdict_io assemble <round_dir> <sidecar_path> "
                         "<rostered_csv>  (extra entries as JSON list on stdin)\n")
        return 2
    round_dir, sidecar_path, rostered_csv = argv[0], argv[1], argv[2]
    rostered = [r.strip() for r in rostered_csv.split(",") if r.strip()]
    extra: list[dict[str, Any]] = []
    raw = ""
    if not sys.stdin.isatty():
        raw = sys.stdin.read()
    if raw.strip():
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                loaded = [loaded]
            extra = [e for e in loaded if isinstance(e, dict)]
        except ValueError:
            extra = []
    entries = assemble_sidecar(round_dir, rostered, extra_entries=extra)
    sp = Path(sidecar_path)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    sys.stdout.write(json.dumps({"ok": True, "written": len(entries),
                                 "path": str(sp)}, ensure_ascii=False) + "\n")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        sys.stderr.write("usage: verdict_io <write|assemble> ...\n")
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "write":
        return _cli_write(rest)
    if cmd == "assemble":
        return _cli_assemble(rest)
    sys.stderr.write(f"unknown subcommand {cmd!r} (want write|assemble)\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
