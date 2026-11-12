#!/usr/bin/env python
"""THE RAW EVIDENCE BUNDLE — one zip per run, everything a skeptic needs.

Leg C bite C4 (PLAN_2026-07-12 §4, the judge's move 2). A converged run leaves its
evidence scattered across the manuscript tree, the git history, the feedback ledger
and the harness transcript directory. A reader who wants to CHECK the run — not
trust the calibration note's prose, but re-derive it — has to know where each
fragment lives. This reader closes that gap: it gathers the run's durable evidence
into ONE self-describing zip under ``<manuscript>/release/bundles/``, indexed by a
``MANIFEST.json`` that names every member with its sha256 — and, crucially, names
every member that is ABSENT, so the skeptic sees what does NOT exist rather than a
silently short bundle.

WHAT A RUN LEAVES BEHIND (the members, reconstructed from the pipeline surfaces):

  * ROUND EVIDENCE — everything under ``<manuscript>/rounds/``: the mechanical
    ``detect_pre``/``detect_post`` panels, the blind ``fix_brief`` briefs, the raw
    ``mech_r*`` finding dumps, the ``adjudicate_*`` machine verdicts, the ``lock_*``
    reader verdicts. The falsifiable trail of what each round caught.
  * THE LOOP-COMMIT LOG — ``git log --stat`` of the ``loop:`` commits in the run
    window. The per-round-accept commits (B5) that bank each incumbent so no
    evidence race can unbank the wave.
  * THE FEEDBACK-LEDGER DELTA — the ``feedback.jsonl`` entries whose timestamp falls
    in the run window: the findings/notes the run appended, isolated from the ledger's
    full history.
  * FINALIZE + PDF METADATA — ``release/finalize.json`` (the named object's title /
    slug / revision / title-agreement check) plus the named PDF's METADATA as text
    (pdfinfo-style: version, page count, embedded /Info, size, sha). NOT the binary
    PDF — the PDF is already a tracked artefact and bundles stay small.
  * ECONOMICS — ``economics.json`` / ``economics.md`` (:mod:`workflow_economics`),
    the per-agent tokens+duration artifact. Taken from disk when the run banked it,
    else generated from the transcript directory at bundle time.
  * LAYOUT-GATE REGISTRY + GATE OUTPUTS — the ``layout_gates.write_registry`` figure
    contract registry and any ``gates.json`` gate outputs, when the run produced them.

Every member is indexed in ``MANIFEST.json`` with ``{arcname, category, present,
sha256, size, source, note}``. A member that could not be resolved is listed with
``present: false`` and a ``reason`` — the honesty contract: absence is documented,
never silently skipped.

IDEMPOTENT + HONEST: re-running with the same label + date never silently
overwrites. Default is to REFUSE (exit 3); ``--on-exists version`` writes the next
``-vN`` sibling instead.

GENERIC: every path is an argument or a conventional probe off the manuscript dir /
the registry. No project name is hardcoded — the same command bundles the SSG run,
a paper_operatorial_loss run, or a synthetics sibling.

THE CALIBRATION-NOTE SEAM: :func:`render_bundle_reference` returns the markdown block
a calibration note embeds (bundle path + manifest digest + member count), in the
:func:`workflow_economics.render_calibration_economics` idiom — so the note points at
the evidence with a checkable digest instead of prose.

Usage:
    python scripts/evidence_bundle.py <manuscript_dir> --label <run-label>
        [--transcript <dir>] [--economics-dir <dir>]
        [--since <iso>] [--until <iso>]
        [--layout-registry <path>] [--gate-output <path> ...]
        [--note <text> ...] [--repo <dir>]
        [--on-exists {refuse,version}] [--date <YYYY-MM-DD>] [--quiet]

Exit contract:
  * 0 — bundle written; MANIFEST indexes present + absent members.
  * 2 — the manuscript directory does not exist (nothing to bundle).
  * 3 — a bundle for this label+date already exists and --on-exists is 'refuse'.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(s: Any) -> Optional[datetime]:
    """A timestamp (ISO string / epoch) as a naive-UTC datetime, or None. Feedback
    ledger ts are naive ISO (``2026-07-10T20:11:34``); we compare in naive UTC."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        v = float(s) / 1000.0 if s > 1e12 else float(s)
        return datetime.utcfromtimestamp(v)
    if isinstance(s, str):
        t = s.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(t)
        except ValueError:
            return None
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    return None


# ---------------------------------------------------------------------------
# a bundle member — either a file to copy or generated bytes
# ---------------------------------------------------------------------------
class Member:
    """One indexed bundle member. Present members carry bytes (from a source file or
    generated in-process); absent members carry a reason and no bytes — the honesty
    contract makes the absence a first-class manifest row."""

    __slots__ = ("arcname", "category", "data", "source", "note", "present", "reason")

    def __init__(self, arcname: str, category: str, *, data: Optional[bytes] = None,
                 source: Optional[str] = None, note: Optional[str] = None,
                 present: bool = True, reason: Optional[str] = None):
        self.arcname = arcname
        self.category = category
        self.data = data
        self.source = source
        self.note = note
        self.present = present
        self.reason = reason

    def manifest_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "arcname": self.arcname,
            "category": self.category,
            "present": self.present,
        }
        if self.present and self.data is not None:
            row["sha256"] = _sha256_bytes(self.data)
            row["size"] = len(self.data)
        if self.source:
            row["source"] = self.source
        if self.note:
            row["note"] = self.note
        if not self.present:
            row["reason"] = self.reason or "not found"
        return row

    @classmethod
    def from_file(cls, arcname: str, category: str, path: Path, *,
                  note: Optional[str] = None) -> "Member":
        return cls(arcname, category, data=path.read_bytes(),
                   source=str(path), note=note)

    @classmethod
    def absent(cls, arcname: str, category: str, reason: str, *,
               source: Optional[str] = None) -> "Member":
        return cls(arcname, category, present=False, reason=reason, source=source)


# ---------------------------------------------------------------------------
# run window
# ---------------------------------------------------------------------------
def resolve_window(transcript_dir: Optional[Path], since: Optional[str],
                   until: Optional[str], pad_s: int = 120
                   ) -> tuple[Optional[datetime], Optional[datetime], str]:
    """The run window [since, until] as naive-UTC datetimes + a description of how it
    was resolved. Explicit ``--since``/``--until`` win; else derived from the min/max
    mtime of the transcript's journal + agent files (padded); else (None, None)."""
    ds, du = _parse_dt(since), _parse_dt(until)
    if ds is not None or du is not None:
        return ds, du, f"explicit (since={since or '-'}, until={until or '-'})"
    if transcript_dir and transcript_dir.is_dir():
        mtimes: list[float] = []
        for p in [transcript_dir / "journal.jsonl", *transcript_dir.glob("agent-*.jsonl")]:
            try:
                mtimes.append(p.stat().st_mtime)
            except OSError:
                continue
        if mtimes:
            lo = datetime.utcfromtimestamp(min(mtimes) - pad_s)
            hi = datetime.utcfromtimestamp(max(mtimes) + pad_s)
            return lo, hi, (f"derived from transcript mtimes "
                            f"[{_iso(lo.replace(tzinfo=timezone.utc))} .. "
                            f"{_iso(hi.replace(tzinfo=timezone.utc))}] (±{pad_s}s)")
    return None, None, "unresolved (no --since/--until and no transcript dir)"


def _in_window(ts: Optional[datetime], lo: Optional[datetime],
               hi: Optional[datetime]) -> bool:
    if ts is None:
        return False
    if lo is not None and ts < lo:
        return False
    if hi is not None and ts > hi:
        return False
    return True


# ---------------------------------------------------------------------------
# loop-commit log
# ---------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, encoding="utf-8",
                              errors="replace", timeout=60)
        return proc.returncode, (proc.stdout or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, f"git error: {e!r}"


def loop_commit_log(repo: Path, lo: Optional[datetime], hi: Optional[datetime]
                    ) -> tuple[str, int]:
    """``git log --stat`` of commits whose subject starts with ``loop:``, bounded to
    the run window when known. Returns (text, count). An empty log is an honest
    artefact (the run made no loop commit in-window), not an error."""
    args = ["log", "-E", "--grep=^loop:", "--stat",
            "--pretty=format:commit %H%nDate:    %cI%nSubject: %s%n"]
    if lo is not None:
        args.append(f"--since={_iso(lo.replace(tzinfo=timezone.utc))}")
    if hi is not None:
        args.append(f"--until={_iso(hi.replace(tzinfo=timezone.utc))}")
    rc, out = _git(repo, *args)
    count = len(re.findall(r"^commit [0-9a-f]{7,}$", out, re.M))
    header = (f"# loop-commit log (git log --stat, subject ^loop:), "
              f"{count} commit(s)\n"
              f"# window: {_iso(lo.replace(tzinfo=timezone.utc)) if lo else '-'} .. "
              f"{_iso(hi.replace(tzinfo=timezone.utc)) if hi else '-'}\n"
              f"# repo: {repo}\n\n")
    if rc != 0:
        return header + f"(git log failed rc={rc})\n{out}", count
    return header + (out if out.strip() else "(no loop: commits in window)\n"), count


# ---------------------------------------------------------------------------
# feedback-ledger delta
# ---------------------------------------------------------------------------
def feedback_delta(ledger: Path, lo: Optional[datetime], hi: Optional[datetime]
                   ) -> tuple[bytes, int, int]:
    """The feedback.jsonl lines whose ``ts`` falls in [lo, hi]. Returns (jsonl bytes,
    kept, total). Lines that don't parse or carry no ts are skipped (counted in total,
    not kept)."""
    kept_lines: list[str] = []
    total = 0
    try:
        text = ledger.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return b"", 0, 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        total += 1
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if _in_window(_parse_dt(rec.get("ts")), lo, hi):
            kept_lines.append(line)
    payload = ("\n".join(kept_lines) + "\n") if kept_lines else ""
    return payload.encode("utf-8"), len(kept_lines), total


# ---------------------------------------------------------------------------
# PDF metadata (pdfinfo-style text) — best-effort, tooling-tolerant
# ---------------------------------------------------------------------------
_PDF_INFO_KEYS = ["Title", "Subject", "Author", "Keywords", "Creator",
                  "Producer", "CreationDate", "ModDate"]


def _pdf_read_string_object(raw: bytes, at: int) -> Optional[str]:
    """Read a PDF string object (literal ``(...)`` with balanced/escaped parens, or
    hex ``<...>``) beginning at the first non-space byte at/after ``at``."""
    i = at
    n = len(raw)
    while i < n and raw[i:i + 1] in (b" ", b"\t", b"\r", b"\n"):
        i += 1
    if i >= n:
        return None
    c = raw[i:i + 1]
    if c == b"(":
        depth = 0
        j = i
        buf = bytearray()
        while j < n:
            ch = raw[j]
            if ch == 0x5C:  # backslash escape
                buf.append(raw[j + 1] if j + 1 < n else 0x5C)
                j += 2
                continue
            if ch == 0x28:  # (
                depth += 1
                if depth > 1:
                    buf.append(ch)
            elif ch == 0x29:  # )
                depth -= 1
                if depth == 0:
                    return buf.decode("latin-1", "replace")
                buf.append(ch)
            else:
                buf.append(ch)
            j += 1
        return buf.decode("latin-1", "replace")
    if c == b"<":
        j = raw.find(b">", i)
        if j < 0:
            return None
        hexs = re.sub(rb"[^0-9A-Fa-f]", b"", raw[i + 1:j])
        if len(hexs) % 2:
            hexs += b"0"
        try:
            return bytes.fromhex(hexs.decode("ascii")).decode("utf-16-be", "replace") \
                if hexs[:2] in (b"FE", b"fe") else bytes.fromhex(hexs.decode("ascii")) \
                .decode("latin-1", "replace")
        except ValueError:
            return None
    return None


def pdf_metadata(pdf_path: Path) -> tuple[str, dict[str, Any]]:
    """Best-effort PDF metadata as pdfinfo-style text + a structured dict. Tries the
    ``pdfinfo`` binary, then ``pikepdf``, then a pure-stdlib byte scan — whichever is
    available. Always reports file size, sha256, PDF version and the extraction method,
    so the metadata is honest about how it was obtained."""
    raw = pdf_path.read_bytes()
    info: dict[str, Any] = {
        "file": pdf_path.name,
        "size_bytes": len(raw),
        "sha256": _sha256_bytes(raw),
        "pdf_version": None,
        "pages": None,
        "docinfo": {},
        "extraction": None,
    }
    m = re.match(rb"%PDF-(\d+\.\d+)", raw[:32])
    if m:
        info["pdf_version"] = m.group(1).decode("ascii")

    # 1) pdfinfo binary --------------------------------------------------------
    import shutil
    if shutil.which("pdfinfo"):
        try:
            proc = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=30)
            if proc.returncode == 0 and proc.stdout.strip():
                info["extraction"] = "pdfinfo"
                for ln in proc.stdout.splitlines():
                    if ":" in ln:
                        k, v = ln.split(":", 1)
                        info["docinfo"][k.strip()] = v.strip()
                        if k.strip() == "Pages":
                            try:
                                info["pages"] = int(v.strip())
                            except ValueError:
                                pass
                return _render_pdfinfo(info), info
        except (OSError, subprocess.SubprocessError):
            pass

    # 2) pikepdf ---------------------------------------------------------------
    try:
        import pikepdf  # type: ignore
        with pikepdf.open(pdf_path) as pk:
            info["extraction"] = "pikepdf"
            info["pages"] = len(pk.pages)
            try:
                info["pdf_version"] = str(pk.pdf_version) or info["pdf_version"]
            except Exception:
                pass
            di = pk.docinfo or {}
            for k in _PDF_INFO_KEYS:
                v = di.get("/" + k)
                if v is not None:
                    info["docinfo"][k] = str(v)
        return _render_pdfinfo(info), info
    except Exception:
        pass

    # 3) pure-stdlib byte scan -------------------------------------------------
    info["extraction"] = "stdlib-besteffort"
    counts = [int(c) for c in re.findall(rb"/Count\s+(\d+)", raw)]
    if counts:
        info["pages"] = max(counts)
    else:
        info["pages"] = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", raw))
    for k in _PDF_INFO_KEYS:
        mk = re.search((r"/" + k + r"\s*").encode("ascii"), raw)
        if mk:
            val = _pdf_read_string_object(raw, mk.end())
            if val:
                info["docinfo"][k] = val
    return _render_pdfinfo(info), info


def _render_pdfinfo(info: dict[str, Any]) -> str:
    lines = [
        f"File:         {info['file']}",
        f"Size (bytes): {info['size_bytes']}",
        f"SHA256:       {info['sha256']}",
        f"PDF version:  {info['pdf_version'] or '-'}",
        f"Pages:        {info['pages'] if info['pages'] is not None else '-'}",
    ]
    for k in _PDF_INFO_KEYS:
        if k in info["docinfo"]:
            lines.append(f"{k + ':':<13} {info['docinfo'][k]}")
    # any extra pdfinfo keys (from the pdfinfo binary path)
    for k, v in info["docinfo"].items():
        if k not in _PDF_INFO_KEYS:
            lines.append(f"{k + ':':<13} {v}")
    lines.append(f"Extraction:   {info['extraction']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# economics — prefer the run's banked artifact, else generate from transcript
# ---------------------------------------------------------------------------
def economics_members(econ_dir: Optional[Path], transcript_dir: Optional[Path]
                      ) -> list[Member]:
    """The economics members. Prefers ``economics.json`` / ``economics.md`` already on
    disk (what the run banked); else generates them from the transcript directory via
    :mod:`workflow_economics`; else lists both absent."""
    out: list[Member] = []
    search = econ_dir or transcript_dir
    found_json = found_md = None
    if search and search.is_dir():
        if (search / "economics.json").is_file():
            found_json = search / "economics.json"
        if (search / "economics.md").is_file():
            found_md = search / "economics.md"

    if found_json:
        out.append(Member.from_file("economics/economics.json", "economics",
                                    found_json, note="banked by the run"))
    if found_md:
        out.append(Member.from_file("economics/economics.md", "economics",
                                    found_md, note="banked by the run"))
    if found_json and found_md:
        return out

    # generate the missing one(s) from the transcript directory
    if transcript_dir and transcript_dir.is_dir():
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import workflow_economics as we  # type: ignore
            econ = we.build_economics(transcript_dir)
            if not found_json:
                data = (json.dumps(econ, indent=2) + "\n").encode("utf-8")
                out.append(Member("economics/economics.json", "economics", data=data,
                                  source=f"generated from {transcript_dir}",
                                  note="generated at bundle time"))
            if not found_md:
                data = we.render_markdown(econ).encode("utf-8")
                out.append(Member("economics/economics.md", "economics", data=data,
                                  source=f"generated from {transcript_dir}",
                                  note="generated at bundle time"))
            return out
        except Exception as e:  # generation is best-effort — never fatal
            if not found_json:
                out.append(Member.absent("economics/economics.json", "economics",
                                         f"generation failed: {e!r}"))
            if not found_md:
                out.append(Member.absent("economics/economics.md", "economics",
                                         f"generation failed: {e!r}"))
            return out

    if not found_json:
        out.append(Member.absent("economics/economics.json", "economics",
                                 "no economics.json on disk and no transcript dir "
                                 "to generate from"))
    if not found_md:
        out.append(Member.absent("economics/economics.md", "economics",
                                 "no economics.md on disk and no transcript dir "
                                 "to generate from"))
    return out


# ---------------------------------------------------------------------------
# layout-gate registry + gate outputs
# ---------------------------------------------------------------------------
def layout_gate_members(manuscript: Path, layout_registry: Optional[Path],
                        gate_outputs: list[Path]) -> list[Member]:
    """The layout-gate registry (``layout_gates.write_registry`` output) + any gate
    outputs. Explicit paths win; else probe the conventional release-dir locations.
    Absent members are listed honestly."""
    out: list[Member] = []
    release = manuscript / "release"

    reg = layout_registry
    if reg is None:
        for cand in (release / "figure_registry.json",
                     release / "layout_registry.json",
                     manuscript / "figure_registry.json"):
            if cand.is_file():
                reg = cand
                break
    if reg and reg.is_file():
        out.append(Member.from_file("layout_gates/registry.json", "layout-gate",
                                    reg))
    else:
        out.append(Member.absent(
            "layout_gates/registry.json", "layout-gate",
            "no layout-gate registry (layout_gates.write_registry) found",
            source=str(layout_registry) if layout_registry else
            str(release / "figure_registry.json")))

    gates = list(gate_outputs)
    if not gates:
        for cand in (release / "gates.json", release / "layout_gates.json"):
            if cand.is_file():
                gates.append(cand)
    if gates:
        for g in gates:
            if g.is_file():
                out.append(Member.from_file(f"layout_gates/{g.name}", "layout-gate", g))
            else:
                out.append(Member.absent(f"layout_gates/{g.name}", "layout-gate",
                                         "gate output path does not exist",
                                         source=str(g)))
    else:
        out.append(Member.absent(
            "layout_gates/gates.json", "layout-gate",
            "no layout-gate outputs (gates.json) found in release/"))
    return out


# ---------------------------------------------------------------------------
# assemble the members
# ---------------------------------------------------------------------------
def collect_members(manuscript: Path, *, transcript_dir: Optional[Path],
                    economics_dir: Optional[Path], repo: Path,
                    lo: Optional[datetime], hi: Optional[datetime],
                    layout_registry: Optional[Path], gate_outputs: list[Path]
                    ) -> tuple[list[Member], dict[str, Any]]:
    """Resolve every bundle member off the manuscript dir + the run window. Returns
    (members, summary) where summary carries the derived counts the reference block
    and the manifest report."""
    members: list[Member] = []
    summary: dict[str, Any] = {}

    # 1) round evidence — every file under rounds/
    rounds = manuscript / "rounds"
    n_rounds = 0
    if rounds.is_dir():
        for p in sorted(rounds.rglob("*")):
            if p.is_file():
                rel = p.relative_to(rounds).as_posix()
                members.append(Member.from_file(f"round_evidence/{rel}",
                                                "round-evidence", p))
                n_rounds += 1
    if n_rounds == 0:
        members.append(Member.absent("round_evidence/", "round-evidence",
                                     f"no rounds/ evidence under {rounds}"))
    summary["round_evidence_files"] = n_rounds

    # 2) loop-commit log
    log_text, n_loop = loop_commit_log(repo, lo, hi)
    members.append(Member("loop_commits.txt", "loop-commits",
                          data=log_text.encode("utf-8"),
                          source=f"git -C {repo} log -E --grep=^loop: --stat",
                          note=f"{n_loop} loop commit(s) in window"))
    summary["loop_commits"] = n_loop

    # 3) feedback-ledger delta
    ledger = manuscript / "feedback" / "feedback.jsonl"
    if ledger.is_file() and (lo is not None or hi is not None):
        data, kept, total = feedback_delta(ledger, lo, hi)
        members.append(Member("feedback_delta.jsonl", "feedback-delta", data=data,
                              source=str(ledger),
                              note=f"{kept} of {total} ledger entries in window"))
        summary["feedback_delta"] = {"kept": kept, "total": total}
    elif not ledger.is_file():
        members.append(Member.absent("feedback_delta.jsonl", "feedback-delta",
                                     f"no feedback ledger at {ledger}"))
        summary["feedback_delta"] = {"kept": 0, "total": 0}
    else:
        members.append(Member.absent("feedback_delta.jsonl", "feedback-delta",
                                     "no run window resolved (need --since/--until "
                                     "or a transcript dir) — cannot scope the delta"))
        summary["feedback_delta"] = {"kept": 0, "total": 0}

    # 4) finalize.json + the named PDF's metadata
    finalize = manuscript / "release" / "finalize.json"
    pdf_name = None
    if finalize.is_file():
        members.append(Member.from_file("release/finalize.json", "finalize", finalize))
        try:
            fin = json.loads(finalize.read_text(encoding="utf-8", errors="replace"))
            pdf_name = fin.get("pdf_path")
            summary["finalize"] = {"slug": fin.get("slug"), "title": fin.get("title"),
                                   "revision": fin.get("revision"), "pdf": pdf_name}
        except (ValueError, OSError):
            pass
    else:
        members.append(Member.absent("release/finalize.json", "finalize",
                                     f"no finalize.json at {finalize}"))

    if pdf_name:
        pdf_path = (manuscript / pdf_name)
        if pdf_path.is_file():
            text, pinfo = pdf_metadata(pdf_path)
            members.append(Member(f"pdf_metadata/{pdf_path.stem}.pdfinfo.txt",
                                  "pdf-metadata", data=text.encode("utf-8"),
                                  source=str(pdf_path),
                                  note=(f"metadata only ({pinfo['extraction']}); the "
                                        "binary PDF is a tracked artefact, not bundled")))
            summary["pdf"] = {"file": pdf_path.name, "sha256": pinfo["sha256"],
                              "pages": pinfo["pages"], "extraction": pinfo["extraction"]}
        else:
            members.append(Member.absent(
                f"pdf_metadata/{Path(pdf_name).stem}.pdfinfo.txt", "pdf-metadata",
                f"finalize names {pdf_name} but it is not on disk",
                source=str(pdf_path)))
    else:
        members.append(Member.absent("pdf_metadata/", "pdf-metadata",
                                     "finalize.json names no pdf_path"))

    # 5) economics
    members.extend(economics_members(economics_dir, transcript_dir))

    # 6) layout-gate registry + gate outputs
    members.extend(layout_gate_members(manuscript, layout_registry, gate_outputs))

    return members, summary


# ---------------------------------------------------------------------------
# build the bundle
# ---------------------------------------------------------------------------
def _resolve_out_path(bundles_dir: Path, label: str, date: str,
                      on_exists: str) -> tuple[Optional[Path], Optional[str]]:
    """The bundle output path. Returns (path, None) when free to write; (None, msg)
    when refusing; (versioned_path, None) when versioning past an existing sibling."""
    base = bundles_dir / f"{label}-evidence-{date}.zip"
    if not base.exists():
        return base, None
    if on_exists == "refuse":
        return None, (f"a bundle already exists: {base} — refusing to overwrite "
                      f"(use --on-exists version to write a -vN sibling)")
    # version: find the next -vN
    n = 2
    while True:
        cand = bundles_dir / f"{label}-evidence-{date}-v{n}.zip"
        if not cand.exists():
            return cand, None
        n += 1


def build_bundle(manuscript: Path, label: str, *, transcript_dir: Optional[Path] = None,
                 economics_dir: Optional[Path] = None, repo: Optional[Path] = None,
                 since: Optional[str] = None, until: Optional[str] = None,
                 layout_registry: Optional[Path] = None,
                 gate_outputs: Optional[list[Path]] = None,
                 notes: Optional[list[str]] = None, date: Optional[str] = None,
                 on_exists: str = "refuse") -> dict[str, Any]:
    """Build the evidence bundle. Returns a result dict
    ``{bundle_path, manifest, manifest_sha256, present, absent, summary}`` — or
    ``{refused: msg}`` when a same-label bundle exists and ``on_exists='refuse'``."""
    manuscript = Path(manuscript)
    repo = Path(repo) if repo else _repo_root(manuscript)
    gate_outputs = gate_outputs or []
    notes = notes or []
    date = date or _now_utc().strftime("%Y-%m-%d")

    bundles_dir = manuscript / "release" / "bundles"
    out_path, refuse = _resolve_out_path(bundles_dir, label, date, on_exists)
    if out_path is None:
        return {"refused": refuse}

    lo, hi, window_desc = resolve_window(transcript_dir, since, until)
    members, summary = collect_members(
        manuscript, transcript_dir=transcript_dir, economics_dir=economics_dir,
        repo=repo, lo=lo, hi=hi, layout_registry=layout_registry,
        gate_outputs=gate_outputs)

    present = [m for m in members if m.present]
    absent = [m for m in members if not m.present]

    manifest = {
        "bundle": out_path.name,
        "label": label,
        "generated_at": _iso(_now_utc()),
        "manuscript_dir": str(manuscript),
        "transcript_dir": str(transcript_dir) if transcript_dir else None,
        "repo": str(repo),
        "git_head": _git(repo, "rev-parse", "HEAD")[1].strip() or None,
        "git_branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD")[1].strip() or None,
        "run_window": {
            "since": _iso(lo.replace(tzinfo=timezone.utc)) if lo else None,
            "until": _iso(hi.replace(tzinfo=timezone.utc)) if hi else None,
            "how": window_desc,
        },
        "summary": summary,
        "notes": notes,
        "member_count": {"present": len(present), "absent": len(absent),
                         "total": len(members)},
        "members": [m.manifest_row() for m in members],
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    manifest_sha = _sha256_bytes(manifest_bytes)

    bundles_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("MANIFEST.json", manifest_bytes)
        for m in present:
            if m.data is not None:
                z.writestr(m.arcname, m.data)

    return {
        "bundle_path": out_path,
        "manifest": manifest,
        "manifest_sha256": manifest_sha,
        "present": [m.arcname for m in present],
        "absent": [{"arcname": m.arcname, "reason": m.reason} for m in absent],
        "summary": summary,
    }


def _repo_root(start: Path) -> Path:
    rc, out = _git(start if start.is_dir() else start.parent,
                   "rev-parse", "--show-toplevel")
    if rc == 0 and out.strip():
        return Path(out.strip())
    return start


# ---------------------------------------------------------------------------
# the calibration-note seam
# ---------------------------------------------------------------------------
def render_bundle_reference(result: dict[str, Any]) -> str:
    """The markdown block a calibration note embeds to point at the evidence bundle:
    the bundle path, the manifest sha256 digest, and the member count (present +
    absent). The consumer seam, in the :func:`workflow_economics.render_calibration_economics`
    idiom — a checkable digest instead of a prose gesture at 'the evidence'."""
    man = result["manifest"]
    mc = man["member_count"]
    s = man.get("summary", {})
    win = man.get("run_window", {})
    fb = s.get("feedback_delta", {}) or {}
    bundle_rel = man["bundle"]
    lines = [
        "### Raw evidence bundle",
        "",
        f"- bundle: `release/bundles/{bundle_rel}` "
        f"({mc['present']} members, {mc['absent']} listed absent)",
        f"- manifest sha256: `{result['manifest_sha256']}`",
        f"- run window: {win.get('since') or '-'} .. {win.get('until') or '-'}",
        f"- covers: round evidence ({s.get('round_evidence_files', 0)} files), "
        f"loop commits ({s.get('loop_commits', 0)}), "
        f"feedback delta ({fb.get('kept', 0)}/{fb.get('total', 0)} in window), "
        f"finalize.json + PDF metadata, economics, layout gates",
    ]
    if man.get("notes"):
        lines.append("- notes: " + " ".join(f"_{n}_" for n in man["notes"]))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Assemble one raw-evidence zip per run under "
                    "<manuscript>/release/bundles/, indexed by MANIFEST.json.")
    ap.add_argument("manuscript", help="the manuscript directory (holds rounds/, "
                    "release/, feedback/)")
    ap.add_argument("--label", required=True, help="the run label (bundle name stem)")
    ap.add_argument("--transcript", default=None,
                    help="the harness transcript dir (journal.jsonl + agent-*.jsonl); "
                    "used to derive the run window and generate economics if absent")
    ap.add_argument("--economics-dir", default=None,
                    help="dir holding economics.{json,md} (default: the transcript dir)")
    ap.add_argument("--since", default=None, help="run window start (ISO)")
    ap.add_argument("--until", default=None, help="run window end (ISO)")
    ap.add_argument("--layout-registry", default=None,
                    help="path to the layout-gate registry (write_registry output)")
    ap.add_argument("--gate-output", action="append", default=[],
                    help="a gate-output json to include (repeatable)")
    ap.add_argument("--note", action="append", default=[],
                    help="an honest run note to record in the manifest (repeatable)")
    ap.add_argument("--repo", default=None, help="git repo root (default: auto-detect)")
    ap.add_argument("--on-exists", choices=["refuse", "version"], default="refuse",
                    help="behaviour when a same-label bundle exists (default: refuse)")
    ap.add_argument("--date", default=None, help="bundle date stamp (default: today)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv[1:])

    manuscript = Path(args.manuscript)
    if not manuscript.is_dir():
        print(f"evidence_bundle: no such manuscript directory: {manuscript}",
              file=sys.stderr)
        return 2

    result = build_bundle(
        manuscript, args.label,
        transcript_dir=Path(args.transcript) if args.transcript else None,
        economics_dir=Path(args.economics_dir) if args.economics_dir else None,
        repo=Path(args.repo) if args.repo else None,
        since=args.since, until=args.until,
        layout_registry=Path(args.layout_registry) if args.layout_registry else None,
        gate_outputs=[Path(p) for p in args.gate_output],
        notes=args.note, date=args.date, on_exists=args.on_exists)

    if "refused" in result:
        print(f"evidence_bundle: {result['refused']}", file=sys.stderr)
        return 3

    if not args.quiet:
        mc = result["manifest"]["member_count"]
        print(f"evidence_bundle: {result['bundle_path']} — "
              f"{mc['present']} members, {mc['absent']} absent · "
              f"manifest sha256 {result['manifest_sha256'][:16]}…")
        if result["absent"]:
            for a in result["absent"]:
                print(f"  absent: {a['arcname']} — {a['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
