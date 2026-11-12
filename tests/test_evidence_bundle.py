"""The raw evidence bundle (scripts/evidence_bundle.py, Leg C bite C4): one zip per
run, everything a skeptic needs, indexed by a MANIFEST.json that names every member
with sha256 AND names every member that is ABSENT.

The pins: (1) a fixture manuscript tree -> a bundle whose every manifest sha matches
the zipped bytes; (2) absent-member honesty (a missing member is LISTED with a
reason, never silently skipped); (3) idempotency (same label+date refuses, or
versions to -vN, never silently overwrites); (4) the feedback-delta window scoping;
(5) the loop-commit log; (6) the calibration-note seam (render_bundle_reference
carries the manifest digest); (7) the stdlib PDF-metadata fallback; (8) the real A6
SSG run's invocation exit code (skipped when the run artefacts are absent)."""
import json
import subprocess
import sys
import zipfile
from hashlib import sha256
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

import evidence_bundle as eb  # noqa: E402


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
_MINIMAL_PDF = b"""%PDF-1.5
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 2 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R >>
endobj
4 0 obj
<< /Title (Fixture Title) /Subject (Fixture Subject) /Keywords (alpha, beta) /Producer (pytest) >>
endobj
trailer
<< /Root 1 0 R /Info 4 0 R >>
%%EOF
"""


def _git(repo, *args, date=None):
    # TZ=UTC: the env is scrubbed, so without it git resolves a bare GIT_*_DATE
    # against /etc/localtime and the commit lands off-window on a non-UTC box.
    # (Belt and braces — callers also pass an explicit offset on `date`.)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "TZ": "UTC",
           "HOME": str(repo), "PATH": __import__("os").environ["PATH"]}
    if date is not None:  # pin the commit inside the run window so --since/--until keep it
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          encoding="utf-8", check=True, env=env)


def _make_manuscript(root: Path, *, with_pdf=True, pdf_on_disk=True) -> Path:
    """A minimal but complete manuscript tree inside a fresh git repo, with one
    ``loop:`` commit so the loop-commit log has something to find. Returns the
    manuscript dir."""
    _git(root, "init", "-q")
    man = root / "manuscript" / "whitepaper"
    (man / "rounds" / "harnessed").mkdir(parents=True)
    (man / "rounds" / "lock_r1").mkdir(parents=True)
    (man / "release").mkdir(parents=True)
    (man / "feedback").mkdir(parents=True)

    # round evidence (nested, mixed json + md)
    (man / "rounds" / "harnessed" / "detect_pre_r1.json").write_text(
        json.dumps({"phase": "pre", "round": 1, "open_findings_n": 9}))
    (man / "rounds" / "harnessed" / "fix_brief_r1.md").write_text("# brief\n- fix x\n")
    (man / "rounds" / "lock_r1" / "R1_verdict.json").write_text(
        json.dumps({"reader": "R1", "clean": False, "findings_n": 2}))
    (man / "rounds" / "lock_r1.json").write_text(json.dumps([{"label": "cold", "clean": False}]))

    # finalize + the named PDF
    pdf_name = "fixture-slug-f.pdf"
    (man / "release" / "finalize.json").write_text(json.dumps({
        "pdf_path": pdf_name, "slug": "fixture-slug-f", "title": "Fixture", "revision": 1}))
    if with_pdf and pdf_on_disk:
        (man / pdf_name).write_bytes(_MINIMAL_PDF)

    # feedback ledger: two entries in-window, one out-of-window
    ledger = man / "feedback" / "feedback.jsonl"
    ledger.write_text("\n".join(json.dumps(r) for r in [
        {"id": "A", "ts": "2026-07-10T20:12:00", "comment": "in-1"},
        {"id": "B", "ts": "2026-07-10T20:15:00", "comment": "in-2"},
        {"id": "C", "ts": "2026-07-09T08:00:00", "comment": "out"},
    ]) + "\n")

    # economics artifacts on disk (a transcript dir)
    tdir = root / "transcript"
    tdir.mkdir()
    (tdir / "economics.json").write_text(json.dumps({"totals": {"agents": 3}}))
    (tdir / "economics.md").write_text("# econ\n")
    (tdir / "journal.jsonl").write_text('{"type":"started"}\n')

    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed the tree", date="2026-07-10T20:10:00+00:00")
    (man / "rounds" / "harnessed" / "detect_post_r2.json").write_text(
        json.dumps({"phase": "post", "round": 2, "open_findings_n": 3}))
    # rounds/ may be gitignored in the real repo; here commit a tracked file for a loop commit
    (man / "release" / "state.json").write_text(json.dumps({"state": "RELEASED"}))
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "loop: fixture-fix-r1 accepted incumbent",
         date="2026-07-10T20:15:00+00:00")
    return man


def _build(man, **kw):
    kw.setdefault("label", "runX")
    kw.setdefault("since", "2026-07-10T20:09:00")
    kw.setdefault("until", "2026-07-10T20:26:00")
    kw.setdefault("date", "2026-07-10")
    kw.setdefault("repo", man.parents[1])
    kw.setdefault("transcript_dir", man.parents[1] / "transcript")
    return eb.build_bundle(man, **kw)


# ---------------------------------------------------------------------------
# 1) bundle + manifest correctness — every present sha matches the zipped bytes
# ---------------------------------------------------------------------------
def test_bundle_and_manifest_sha_correctness(tmp_path):
    man = _make_manuscript(tmp_path)
    res = _build(man)
    bpath = res["bundle_path"]
    assert bpath.is_file()

    with zipfile.ZipFile(bpath) as z:
        names = set(z.namelist())
        assert "MANIFEST.json" in names
        manifest = json.loads(z.read("MANIFEST.json"))
        present = [m for m in manifest["members"] if m["present"]]
        # every present member is in the zip and its sha matches the bytes
        for m in present:
            assert m["arcname"] in names, m["arcname"]
            assert sha256(z.read(m["arcname"])).hexdigest() == m["sha256"]
            assert z.getinfo(m["arcname"]).file_size == m["size"]
        # the zip holds exactly the present members plus MANIFEST.json
        assert len(names) == len(present) + 1
        # member_count is internally consistent
        mc = manifest["member_count"]
        assert mc["present"] == len(present)
        assert mc["total"] == len(manifest["members"])
        assert mc["present"] + mc["absent"] == mc["total"]
    # the round evidence subtree is preserved
    assert any(m["arcname"] == "round_evidence/harnessed/detect_pre_r1.json"
               for m in manifest["members"])
    # economics came from disk
    assert any(m["arcname"] == "economics/economics.json" and m["present"]
               for m in manifest["members"])
    assert manifest["summary"]["loop_commits"] >= 1


# ---------------------------------------------------------------------------
# 2) absent-member honesty — a missing member is LISTED with a reason
# ---------------------------------------------------------------------------
def test_absent_members_listed_not_skipped(tmp_path):
    # PDF named by finalize but NOT on disk -> its metadata must be listed absent
    man = _make_manuscript(tmp_path, pdf_on_disk=False)
    res = _build(man)
    absent = {a["arcname"]: a["reason"] for a in res["absent"]}
    # the layout-gate registry + gate outputs are absent (never produced here)
    assert any("layout_gates/registry.json" == k for k in absent)
    assert any(k.startswith("layout_gates/gates") for k in absent)
    # the PDF metadata is absent with a reason naming the missing file
    pdf_absent = [k for k in absent if k.startswith("pdf_metadata/")]
    assert pdf_absent, "the missing PDF must be listed absent, not skipped"
    assert "not on disk" in absent[pdf_absent[0]]
    # every absent member carries a non-empty reason in the manifest
    with zipfile.ZipFile(res["bundle_path"]) as z:
        manifest = json.loads(z.read("MANIFEST.json"))
    for m in manifest["members"]:
        if not m["present"]:
            assert m.get("reason"), m["arcname"]
            assert "sha256" not in m  # absent members have no sha


# ---------------------------------------------------------------------------
# 3) idempotency — refuse, and version, never silent overwrite
# ---------------------------------------------------------------------------
def test_refuse_then_version_on_existing_label(tmp_path):
    man = _make_manuscript(tmp_path)
    first = _build(man)
    assert "bundle_path" in first
    original_bytes = first["bundle_path"].read_bytes()

    # default: refuse (never overwrite)
    refused = _build(man)
    assert "refused" in refused
    assert "refusing to overwrite" in refused["refused"]
    # the original is untouched
    assert first["bundle_path"].read_bytes() == original_bytes

    # opt-in: version to -v2
    versioned = _build(man, on_exists="version")
    assert "bundle_path" in versioned
    assert versioned["bundle_path"] != first["bundle_path"]
    assert versioned["bundle_path"].name.endswith("-v2.zip")
    assert first["bundle_path"].read_bytes() == original_bytes  # still untouched


def test_cli_refuse_returns_exit_3(tmp_path):
    man = _make_manuscript(tmp_path)
    argv = ["evidence_bundle.py", str(man), "--label", "cli", "--date", "2026-07-10",
            "--repo", str(tmp_path), "--since", "2026-07-10T20:09:00",
            "--until", "2026-07-10T20:26:00", "--quiet"]
    assert eb.main(argv) == 0
    assert eb.main(argv) == 3  # second identical call refuses


# ---------------------------------------------------------------------------
# 4) feedback-delta window scoping
# ---------------------------------------------------------------------------
def test_feedback_delta_scoped_to_window(tmp_path):
    man = _make_manuscript(tmp_path)
    res = _build(man)
    with zipfile.ZipFile(res["bundle_path"]) as z:
        delta = z.read("feedback_delta.jsonl").decode().strip().splitlines()
        manifest = json.loads(z.read("MANIFEST.json"))
    ids = {json.loads(l)["id"] for l in delta}
    assert ids == {"A", "B"}          # the two in-window; "C" excluded
    assert manifest["summary"]["feedback_delta"] == {"kept": 2, "total": 3}


def test_feedback_delta_absent_without_window(tmp_path):
    man = _make_manuscript(tmp_path)
    # no window + no transcript -> the delta cannot be scoped -> listed absent
    res = eb.build_bundle(man, label="nowin", date="2026-07-10", repo=tmp_path,
                          transcript_dir=None, since=None, until=None)
    absent = {a["arcname"] for a in res["absent"]}
    assert "feedback_delta.jsonl" in absent


# ---------------------------------------------------------------------------
# 5) loop-commit log
# ---------------------------------------------------------------------------
def test_loop_commit_log_captured(tmp_path):
    man = _make_manuscript(tmp_path)
    res = _build(man)
    with zipfile.ZipFile(res["bundle_path"]) as z:
        log = z.read("loop_commits.txt").decode()
    assert "loop: fixture-fix-r1 accepted incumbent" in log
    assert "seed the tree" not in log            # non-loop commit excluded
    assert res["manifest"]["summary"]["loop_commits"] == 1


# ---------------------------------------------------------------------------
# 6) the calibration-note seam
# ---------------------------------------------------------------------------
def test_render_bundle_reference_carries_digest(tmp_path):
    man = _make_manuscript(tmp_path)
    res = _build(man)
    md = eb.render_bundle_reference(res)
    assert "Raw evidence bundle" in md
    assert res["manifest_sha256"] in md          # the checkable digest
    assert res["bundle_path"].name in md
    # member count present + absent surfaced
    mc = res["manifest"]["member_count"]
    assert str(mc["present"]) in md and str(mc["absent"]) in md
    assert "feedback delta (2/3 in window)" in md


# ---------------------------------------------------------------------------
# 7) the stdlib PDF-metadata fallback
# ---------------------------------------------------------------------------
def test_pdf_metadata_stdlib_fallback(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(_MINIMAL_PDF)
    text, info = eb.pdf_metadata(p)
    assert info["sha256"] == sha256(_MINIMAL_PDF).hexdigest()
    assert info["pdf_version"] == "1.5"
    assert info["pages"] == 2
    assert info["docinfo"].get("Title") == "Fixture Title"
    assert info["docinfo"].get("Keywords") == "alpha, beta"
    assert "SHA256:" in text and "Pages:" in text
    # extraction method is honest (pdfinfo/pikepdf may be present in some envs)
    assert info["extraction"] in ("pdfinfo", "pikepdf", "stdlib-besteffort")


# ---------------------------------------------------------------------------
# 8) the real A6 SSG run — its invocation exit code
# ---------------------------------------------------------------------------
_REAL_MAN = REPO / "synthetics papers/subset-sum-itqde/manuscript/whitepaper"
_REAL_TRANSCRIPT = Path(
    "/root/.claude/projects/-home-user-laplace/fa555552-f5a0-576f-931a-84b12f7d3cb6"
    "/subagents/workflows/wf_8e736fed-947")


def _is_dir_readable(p: Path) -> bool:
    """``p.is_dir()``, but *unreadable* also counts as absent.

    ``_REAL_TRANSCRIPT`` is a recorded absolute path from the container the run was
    captured on. ``Path.is_dir()`` only swallows ENOENT/ENOTDIR/EBADF/ELOOP, so on a
    box where an ancestor is unreadable (``/root`` is mode 0700 and we are not root)
    the stat raises PermissionError instead of returning False. Treat any OSError as
    "not there", so the test takes its ``--since/--until`` fallback branch.
    """
    try:
        return p.is_dir()
    except OSError:
        return False


@pytest.mark.skipif(not (_REAL_MAN / "release" / "finalize.json").is_file(),
                    reason="the real SSG run artefacts are not present")
def test_real_run_invocation_exit_code():
    # a unique label so we never collide with the shipped a6-ssg-run1 bundle
    argv = ["evidence_bundle.py", str(_REAL_MAN), "--label", "pytest-real-probe",
            "--on-exists", "version", "--quiet"]
    if _is_dir_readable(_REAL_TRANSCRIPT):
        argv += ["--transcript", str(_REAL_TRANSCRIPT)]
    else:
        argv += ["--since", "2026-07-10T20:09:00", "--until", "2026-07-10T20:26:00"]
    rc = eb.main(argv)
    assert rc == 0
    # clean up the probe bundles so the test leaves no artefact behind
    for p in (_REAL_MAN / "release" / "bundles").glob("pytest-real-probe-*.zip"):
        p.unlink()
