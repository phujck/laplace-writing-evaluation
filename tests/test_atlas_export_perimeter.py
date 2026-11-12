"""test_atlas_export_perimeter.py - the CONTENT seal of a travelling bundle, on planted nodes.

WHY THIS FILE IS ON THE LAPLACE SIDE. The two existing seal tests guard the IMPORT seal, in both
directions: ``tests/test_atlas_seal.py`` (the engine never imports atlas) and
``atlas/tests/test_seal.py`` (atlas never imports laplace). Neither touches the content seal,
because the content seal does not execute in either of those trees - it executes in
``scripts/export_atlas_snapshot.py``, which is laplace-side by construction (it imports
``laplace.engine.self_shard`` for the node universe and imports nothing from atlas). A test of
``is_sealed`` / ``node_record`` / ``export`` therefore has to live here; putting it under
``atlas/tests/`` would mean atlas importing the exporter, which is the very thing the import
seal forbids.

WHAT IS PLANTED, AND WHY PLANTED RATHER THAN ASSERTED. The perimeter is only worth what it does
to a file it has never seen, so the fixture builds a THROWAWAY tree in ``tmp_path`` carrying a
small never-public profile at one of the declared paths, exports it through the real
``export()``, and then reads the produced bundle back as a stranger would - every byte of every
file it wrote - asking whether the planted sentence is anywhere in it. Two controls keep the
assertion from being vacuous: an outward-facing profile (the Jack-profile shape, sent by the
author's own hand, carrying no never-public declaration) must come through the same export WITH
its content, and a sealed row carrying a blob must make the export refuse.

Written 2026-08-13 with the perimeter fix that added ``NEVER_PUBLIC_PATHS`` - the two profiles
that had been riding the banked bundles unsealed. See
``evidence/SEV_2026-08-13_profile-perimeter/README.md``.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_atlas_snapshot as exporter  # noqa: E402 - the perimeter under test


@pytest.mark.parametrize("refused", [True, False])
def test_exporter_process_status_on_planted_refusal(tmp_path, refused):
    """Exercise the CLI exit, full refusal list, and absence of partial output."""
    repo = tmp_path / "source"
    repo.mkdir()
    for i in range(8):
        (repo / f"record-{i}.md").write_text(
            "soul/plant\n" * 101 if refused else "Ordinary source.\n", encoding="utf-8"
        )
    out = tmp_path / "bundle"
    # Only provenance is planted; classification, density, write path and main are real.
    driver = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import export_atlas_snapshot as e
e.ROOT = Path(sys.argv[2])
e.commit_sha = lambda root: '0' * 40
e.head_blobs = lambda root: {
    p.name: e.git_blob_sha(p.read_bytes()) for p in root.iterdir()
}
raise SystemExit(e.main(['--full', '--with-blobs', '--out-dir', sys.argv[3]]))
"""
    result = subprocess.run(
        [sys.executable, "-c", driver, str(ROOT / "scripts"), str(repo), str(out)],
        capture_output=True, text=True, check=False,
    )
    if refused:
        assert result.returncode == 2, result
        assert result.stdout == ""
        assert "REFUSED 8 unsealed node(s)" in result.stderr
        for i in range(8):
            assert f"record-{i}.md (101 refs)" in result.stderr
        assert not out.exists()
    else:
        assert result.returncode == 0, result
        assert result.stderr == ""
        assert len(list(out.glob("*/manifest.json"))) == 1


def test_derived_directories_seal_descendants_without_reading(tmp_path, monkeypatch):
    repo = tmp_path / "source"
    prefix = "evidence/EMBEDDING_BAKEOFF_2026-08-19/bge-base/"
    rel = prefix + "nested/new-derived.json"
    path = repo / rel
    path.parent.mkdir(parents=True)
    path.write_text('"private derived content"', encoding="utf-8")
    original_open = Path.open

    def guarded_open(self, *args, **kwargs):
        assert self != path, "sealed derived directory was opened"
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(exporter, "commit_sha", lambda root: "0" * 40)
    monkeypatch.setattr(exporter, "head_blobs", lambda root: {rel: "presence-only"})
    out = exporter.export(repo, tmp_path / "bundle", full=True)
    row = _rows(out["path"])[rel]
    assert row["sealed"] and row["content_blob"] is None
    assert prefix in out["manifest"]["sealed_paths"]
    assert prefix in out["manifest"]["sealed_prefixes"]
    assert out["seal_report"]["declaration_heads_read"] == 0
    assert not exporter.is_sealed(prefix.rstrip("/") + "-other/source.py")
    assert not exporter.is_sealed("evidence/EMBEDDING_BAKEOFF_2026-08-19/bakeoff.py")


#: The planted document's giveaway. Distinctive enough that an incidental match means something.
PLANTED_SECRET = "The planted never-public sentence that must never reach a travelling bundle."
PLANTED_BODY = (
    "# A planted profile\n\n"
    "> **NEVER-PUBLIC - engine-repo only.** This file must never enter any bundle, export,\n"
    "> website, talk, disclosure, or manuscript.\n\n"
    f"{PLANTED_SECRET}\n"
)

#: An outward artifact of the same shape and directory, carrying no declaration. The control.
OUTWARD_SECRET = "An outward operating profile, sent by the author's own hand, and quotable."
OUTWARD_BODY = f"# An operating profile\n\n{OUTWARD_SECRET}\n"


#: THE FOURTH CLASS'S OWN PLANT. Same declaration, at a path NO literal list has ever named, in a
#: directory that is not ``profiles/``. Only the head scan can reach it - which is the whole of
#: WO-20260814-autoseal-by-declaration: the file written after the last judge read the corpus.
UNLISTED_REL = "reports/NEW_PROFILE_2026-08-21_written-after-the-list.md"
UNLISTED_SECRET = "An unlisted document that declares itself and was never transcribed anywhere."
UNLISTED_BODY = (
    "# A profile nobody added to a tuple\n\n"
    "> **NEVER-PUBLIC — engine-repo only.** Written after the last hand-edit of the seal list.\n\n"
    f"{UNLISTED_SECRET}\n"
)
#: Its LaTeX rendering, whose banner hides behind three macros, and whose escaped prose would not
#: match a fingerprint drawn from the .md. The .pdf can declare nothing at all - it is never read
#: as text - so it is reachable only by the sibling rule.
UNLISTED_TEX_REL = "reports/NEW_PROFILE_2026-08-21_written-after-the-list.tex"
UNLISTED_TEX_SECRET = "An unlisted document, LaTeX-escaped, still never public."
UNLISTED_TEX_BODY = (
    "\\documentclass{article}\n\\begin{document}\n"
    "{\\small\\textcolor{gray}{\\textbf{NEVER-PUBLIC --- sealed class, engine-repo only.}}}\n\n"
    f"{UNLISTED_TEX_SECRET}\n\\end{{document}}\n"
)
UNLISTED_PDF_REL = "reports/NEW_PROFILE_2026-08-21_written-after-the-list.pdf"

#: THE DISCRIMINATOR. Prose ABOUT the declaration, of the kind every session handoff and every
#: seal instrument in this repository contains. It must NOT bind, or the grammar seals the record
#: of the perimeter along with the perimeter.
DISCUSSION_REL = "SESSION_HANDOFF_planted_discussion.md"
DISCUSSION_SECRET = "Prose about the perimeter, which is ordinary record and must stay readable."
DISCUSSION_BODY = (
    "# A session handoff\n\n"
    "3. **The perimeter by-catch, fixed same night** (R9): the psych profile (in-band\n"
    "   never-public) rode all five banked bundles unsealed; engine-repo only was what its\n"
    "   own header said, and nobody had transcribed it.\n\n"
    f"{DISCUSSION_SECRET}\n"
)


def _fixture_tree(tmp_path: Path) -> Path:
    """A throwaway repo-shaped tree: the listed plant, the unlisted plant, and two controls."""
    repo = tmp_path / "planted_repo"
    (repo / "profiles").mkdir(parents=True)
    (repo / "reports").mkdir(parents=True)
    (repo / "profiles" / Path(exporter.NEVER_PUBLIC_PATHS[0]).name).write_text(
        PLANTED_BODY, encoding="utf-8"
    )
    (repo / UNLISTED_REL).write_text(UNLISTED_BODY, encoding="utf-8")
    (repo / UNLISTED_TEX_REL).write_text(UNLISTED_TEX_BODY, encoding="utf-8")
    (repo / UNLISTED_PDF_REL).write_bytes(b"%PDF-1.4 not text, and it names the document\n")
    (repo / DISCUSSION_REL).write_text(DISCUSSION_BODY, encoding="utf-8")
    (repo / "DRAFT_outward-operating-profile.md").write_text(OUTWARD_BODY, encoding="utf-8")
    (repo / "README.md").write_text("Ordinary record, read and blobbed as usual.\n",
                                    encoding="utf-8")
    return repo


def _export_without_git(monkeypatch, repo: Path, out_dir: Path):
    """Run the REAL export against a tree that is not a git repo.

    Only the two git probes are replaced, and ``head_blobs`` is answered truthfully from the
    fixture's own bytes so ``tree_dirty`` is false and no refusal fires for the wrong reason.
    Everything the test is about - ``node_universe``, ``is_sealed``, ``node_record``, the seal
    counts, the refusals, both write passes - is the shipped code.
    """
    monkeypatch.setattr(exporter, "commit_sha", lambda _root: "0" * 40)

    def _head(root: Path) -> dict[str, str]:
        return {
            rel: exporter.git_blob_sha((root / rel).read_bytes())
            for rel in exporter.node_universe(root)
            if (root / rel).is_file()
        }

    monkeypatch.setattr(exporter, "head_blobs", _head)
    return exporter.export(repo, out_dir, full=True, with_blobs=True)


def _bundle_bytes(bundle: Path) -> bytes:
    """Every byte the export wrote, blobs included - the bundle as a stranger receives it."""
    return b"".join(
        p.read_bytes() for p in sorted(bundle.rglob("*")) if p.is_file()
    )


def _rows(bundle: Path) -> dict[str, dict]:
    out = {}
    with open(bundle / "nodes.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                out[row["node_id"]] = row
    return out


# ---------------------------------------------------------------------------
# the declared perimeter
# ---------------------------------------------------------------------------

def test_never_public_paths_are_declared_and_sealed():
    assert exporter.NEVER_PUBLIC_PATHS, "the never-public list is empty; the perimeter is gone"
    for rel in exporter.NEVER_PUBLIC_PATHS:
        assert exporter.is_sealed(rel), f"{rel} declares itself never-public and is not sealed"
        assert rel in exporter.EXTRA_SEALED_PATHS, (
            f"{rel} is sealed but absent from the hashed manifest perimeter"
        )


def test_never_public_paths_still_exist_in_the_tree():
    """A perimeter naming files that have moved is a perimeter that silently stopped working."""
    missing = [rel for rel in exporter.NEVER_PUBLIC_PATHS if not (ROOT / rel).is_file()]
    assert not missing, f"never-public paths named but absent (renamed? moved?): {missing}"


def test_the_outward_profile_is_not_sealed():
    """The seal follows the declaration, never the directory. Sent-by-hand artifacts stay open."""
    for rel in ("DRAFT_2026-08-12_jack-hampson-operating-profile.md",
                "DRAFT_2026-08-12_jack-hampson-operating-profile.tex",
                "profiles/voice/gerard-technical-v1.md"):
        assert not exporter.is_sealed(rel), f"{rel} carries no never-public declaration"


def test_excerpt_carriers_are_declared_sealed_and_present():
    """The third class: derived stores carrying sealed content verbatim (the law's own founding
    measurement). The clean fifth transcript of the same run stays open - measurement, not
    directory, decides."""
    assert exporter.EXCERPT_CARRIER_PATHS, "the excerpt-carrier list is empty; the class is gone"
    for rel in exporter.EXCERPT_CARRIER_PATHS:
        assert exporter.is_sealed(rel), f"{rel} carries sealed excerpts and is not sealed"
        assert rel in exporter.EXTRA_SEALED_PATHS
    missing = [rel for rel in exporter.EXCERPT_CARRIER_PATHS if not (ROOT / rel).is_file()]
    assert not missing, f"excerpt-carrier paths named but absent: {missing}"
    clean = "eigenengine/manuscript/rounds/harnessed/econ_run_2026-07-13_growth/agent-a5fc4c5d712de307f.jsonl"
    assert not exporter.is_sealed(clean), "the measured-clean transcript must stay open"


# ---------------------------------------------------------------------------
# the planted node, through the real export
# ---------------------------------------------------------------------------

def test_planted_never_public_node_is_sealed_refs_only(tmp_path, monkeypatch):
    repo = _fixture_tree(tmp_path)
    planted = exporter.NEVER_PUBLIC_PATHS[0]
    assert planted in exporter.node_universe(repo), "the planted node is not in the universe"

    out = _export_without_git(monkeypatch, repo, tmp_path / "stores")
    rows = _rows(out["path"])

    row = rows[planted]
    assert row["sealed"] is True
    assert row["read_policy"] == "sealed-refs-only"
    assert row["content_hash"] == exporter.REFS_ONLY
    assert row["content_blob"] is None
    assert row["size_bytes"] == 0, "size is a read of the file; a sealed node is never stat'ed"


def test_the_planted_secret_is_nowhere_in_the_bundle(tmp_path, monkeypatch):
    """The property that matters, checked over every byte the export wrote, blobs included."""
    repo = _fixture_tree(tmp_path)
    out = _export_without_git(monkeypatch, repo, tmp_path / "stores")
    written = _bundle_bytes(out["path"])
    assert PLANTED_SECRET.encode("utf-8") not in written
    assert b"must never enter any bundle" not in written
    # not vacuous: the control's text IS there, so the scan is looking in the right place
    assert OUTWARD_SECRET.encode("utf-8") in written


def test_the_outward_control_is_exported_with_content(tmp_path, monkeypatch):
    repo = _fixture_tree(tmp_path)
    out = _export_without_git(monkeypatch, repo, tmp_path / "stores")
    row = _rows(out["path"])["DRAFT_outward-operating-profile.md"]
    assert row["sealed"] is False
    assert row["read_policy"] == "text"
    assert row["content_blob"] is not None
    assert row["size_bytes"] == len(OUTWARD_BODY.encode("utf-8"))


def test_seal_report_and_manifest_carry_the_never_public_perimeter(tmp_path, monkeypatch):
    """The widening is part of the bundle's identity, so reverting it is visible in the id."""
    repo = _fixture_tree(tmp_path)
    out = _export_without_git(monkeypatch, repo, tmp_path / "stores")
    manifest = json.loads((out["path"] / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((out["path"] / "seal_report.json").read_text(encoding="utf-8"))

    for rel in exporter.NEVER_PUBLIC_PATHS:
        assert rel in manifest["sealed_paths"]
    assert report["exporter_never_public_paths"] == list(exporter.NEVER_PUBLIC_PATHS)
    assert report["soul_paths_with_content"] == 0
    assert report["bytes_read_from_sealed"] == 0
    assert report["sealed_nodes"] == manifest["sealed_node_count"] >= 1


# ---------------------------------------------------------------------------
# the fourth class: auto-seal by the file's own declaration
# (WO-20260814-autoseal-by-declaration, landed 2026-08-21)
# ---------------------------------------------------------------------------

def test_the_grammar_binds_a_banner_and_not_prose_about_one():
    """The five clauses, on bytes, without an export in the way.

    The negative half is the point: every seal instrument in this repository, every session
    handoff that records a perimeter fix, and this test file itself carry the token. A grammar
    that seals the record of the perimeter along with the perimeter is worse than no grammar.
    """
    binds = [
        b"> **NEVER-PUBLIC - engine-repo only.** This file must never enter any bundle.",
        b"NEVER PUBLIC: must never enter any bundle, export, website, talk or manuscript.",
        b"{\\small\\textcolor{gray}{\\textbf{NEVER-PUBLIC --- sealed class, engine-repo only.}}}",
        b"# NEVER-PUBLIC\n# engine-repo only, and it must never travel.",
    ]
    for head in binds:
        assert exporter.declaration_binds(head), f"a banner did not bind: {head[:48]!r}"

    prose = [
        # clause 4, and the one a re-wrap of the live handoff would otherwise have sealed
        b"   never-public) rode all five banked bundles unsealed; engine-repo only was what",
        # clause 3: the token as a noun, deep in a numbered sentence
        b"3. The perimeter by-catch, fixed same night: the psych profile was in-band "
        b"never-public and engine-repo only, and nobody had transcribed it.",
        # clause 5: the topic without an instruction
        b"> **NEVER-PUBLIC** is the class of file this scan exists to find.",
        # clause 1 is tested through the window, not here: the token simply absent
        b"An ordinary paragraph of record with no declaration in it at all.",
    ]
    for head in prose:
        assert exporter.declaration_binds(head) is None, f"prose bound: {head[:48]!r}"


def test_the_window_is_the_head_only():
    """A declaration is a banner. The same sentence 4 KB down is a quotation of one."""
    banner = b"> **NEVER-PUBLIC - engine-repo only.** It must never enter any bundle.\n"
    assert exporter.declaration_binds(banner)
    buried = b"x" * (exporter.DECLARATION_WINDOW_BYTES + 10) + banner
    assert exporter.declaration_binds(buried[:exporter.DECLARATION_WINDOW_BYTES]) is None


def test_an_unlisted_declaring_node_is_sealed_refs_only(tmp_path, monkeypatch):
    """The whole work order in one assertion: a file no list names, sealed by its own header."""
    repo = _fixture_tree(tmp_path)
    assert UNLISTED_REL not in exporter.EXTRA_SEALED_PATHS, "the plant must be unlisted"
    assert not exporter.is_sealed(UNLISTED_REL), "the literal perimeter must not reach it"

    out = _export_without_git(monkeypatch, repo, tmp_path / "stores")
    rows = _rows(out["path"])
    for rel in (UNLISTED_REL, UNLISTED_TEX_REL, UNLISTED_PDF_REL):
        row = rows[rel]
        assert row["sealed"] is True, f"{rel} declared itself and travelled anyway"
        assert row["read_policy"] == "sealed-refs-only"
        assert row["content_hash"] == exporter.REFS_ONLY
        assert row["content_blob"] is None
        assert row["size_bytes"] == 0

    written = _bundle_bytes(out["path"])
    assert UNLISTED_SECRET.encode("utf-8") not in written
    assert UNLISTED_TEX_SECRET.encode("utf-8") not in written
    # not vacuous: the discussion node and the outward control both came through with content
    assert DISCUSSION_SECRET.encode("utf-8") in written
    assert OUTWARD_SECRET.encode("utf-8") in written


def test_the_discussion_node_is_not_sealed(tmp_path, monkeypatch):
    """Record ABOUT the perimeter stays readable, and is reported as a near miss, not dropped."""
    repo = _fixture_tree(tmp_path)
    out = _export_without_git(monkeypatch, repo, tmp_path / "stores")
    row = _rows(out["path"])[DISCUSSION_REL]
    assert row["sealed"] is False
    assert row["read_policy"] == "text"
    report = json.loads((out["path"] / "seal_report.json").read_text(encoding="utf-8"))
    assert DISCUSSION_REL in report["declaration_near_miss_paths"]
    assert DISCUSSION_REL not in report["declaration_sealed_paths"]


def test_the_seal_report_names_the_declaration_perimeter(tmp_path, monkeypatch):
    """Paths and counts only - the report must never quote a syllable of what it sealed."""
    repo = _fixture_tree(tmp_path)
    out = _export_without_git(monkeypatch, repo, tmp_path / "stores")
    report = json.loads((out["path"] / "seal_report.json").read_text(encoding="utf-8"))
    manifest = json.loads((out["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert UNLISTED_REL in report["declaration_declared_paths"]
    assert UNLISTED_TEX_REL in report["declaration_declared_paths"]
    assert UNLISTED_PDF_REL in report["declaration_rendering_paths"]
    assert UNLISTED_REL in report["declaration_paths_new_to_the_literal_lists"]
    # the widened perimeter is part of the bundle's identity, exactly like the literal lists
    for rel in (UNLISTED_REL, UNLISTED_TEX_REL, UNLISTED_PDF_REL):
        assert rel in manifest["sealed_paths"]
    assert report["declaration_posture"] == "seal-and-report"
    assert report["declaration_heads_read"] >= 3
    assert report["declaration_head_bytes_read_from_declared"] > 0
    assert report["bytes_read_from_sealed"] == 0, "content is still never read from a sealed node"

    # the "why" comes from the exporter's own closed vocabulary, never from the scanned bytes
    vocabulary = {label for label, _ in exporter.DECLARATION_QUALIFIERS}
    assert set(report["declaration_declared_paths"].values()) <= vocabulary
    blob = json.dumps(report, ensure_ascii=False).encode("utf-8")
    assert UNLISTED_SECRET.encode("utf-8") not in blob
    assert UNLISTED_TEX_SECRET.encode("utf-8") not in blob


def test_refuse_on_declaration_is_the_other_posture(tmp_path, monkeypatch):
    """His call, one flag away, and it must refuse BEFORE anything reaches the disk."""
    repo = _fixture_tree(tmp_path)
    stores = tmp_path / "stores"
    monkeypatch.setattr(exporter, "commit_sha", lambda _root: "0" * 40)
    monkeypatch.setattr(exporter, "head_blobs", lambda root: {
        rel: exporter.git_blob_sha((root / rel).read_bytes())
        for rel in exporter.node_universe(root) if (root / rel).is_file()
    })
    with pytest.raises(exporter.ExportRefusal, match="declare themselves never-public"):
        exporter.export(repo, stores, refuse_on_declaration=True, full=True)
    assert not list(stores.glob("*/nodes.jsonl")), "a refused export left a bundle behind"


def test_the_scan_reproduces_the_hand_list_on_the_live_tree():
    """The measured agreement, and the one path that proves the list still earns its place.

    Five of the six ``NEVER_PUBLIC_PATHS`` are reachable by head scan alone (two declaring .md,
    one declaring .tex, two .pdf renderings by the sibling rule). The sixth,
    ``profiles/gerard_mini_conceptric_v1.json``, declares nothing in its own head - its note
    lives in a companion - so no scan can reach it. That is why the scan runs BESIDE the lists
    and never instead of them.
    """
    scan = exporter.scan_declarations(ROOT, sorted(set(exporter.NEVER_PUBLIC_PATHS) | {
        "scripts/export_atlas_snapshot.py", "scripts/verify_seal_fingerprints.py",
        "tests/test_atlas_export_perimeter.py"}))
    sealed = set(scan["sealed"])
    unreachable = sorted(set(exporter.NEVER_PUBLIC_PATHS) - sealed)
    assert unreachable == ["profiles/gerard_mini_conceptric_v1.json"], (
        "the scan's reach over the hand list moved; re-measure before changing this expectation"
    )
    # nothing under a sealed prefix is ever opened by the scan
    assert not [rel for rel in scan["near_misses"] if rel.startswith(exporter.SEALED_PREFIXES)]
    # and the machinery that DISCUSSES the perimeter is near-missed, never sealed
    for rel in ("scripts/export_atlas_snapshot.py", "scripts/verify_seal_fingerprints.py",
                "tests/test_atlas_export_perimeter.py"):
        assert rel not in sealed, f"{rel} writes about the perimeter and must stay readable"


# ---------------------------------------------------------------------------
# the refusal, when something upstream hands the writer a leaking row
# ---------------------------------------------------------------------------

def test_export_refuses_a_sealed_row_that_carries_content(tmp_path, monkeypatch):
    """The seal is computed from the rows before any write; a leaking bundle never reaches disk."""
    repo = _fixture_tree(tmp_path)
    planted = exporter.NEVER_PUBLIC_PATHS[0]
    real = exporter.node_record

    def _leaky(root, rel, declared=frozenset()):
        if rel == planted:                    # a sealed row that smuggled a blob through
            data = (root / rel).read_bytes()
            key = exporter.hash_bytes(data)
            return ({"schema_version": exporter.SNAPSHOT_NODE_SCHEMA, "node_id": rel,
                     "path": rel, "kind": "soul", "sealed": True, "is_text": True,
                     "read_policy": "text", "content_hash": key, "content_blob": key,
                     "size_bytes": len(data)}, data)
        return real(root, rel, declared)

    monkeypatch.setattr(exporter, "node_record", _leaky)
    stores = tmp_path / "stores"
    with pytest.raises(exporter.ExportRefusal, match="sealed node"):
        _export_without_git(monkeypatch, repo, stores)
    assert not list(stores.glob("*/nodes.jsonl")), "a refused export left a bundle behind"


@pytest.fixture()
def incremental_repo(tmp_path, monkeypatch):
    repo = tmp_path / "source"
    repo.mkdir()
    for name, body in {"keep.md": "Kept.\n", "edit.md": "Before.\n", "drop.md": "Drop.\n"}.items():
        (repo / name).write_text(body)
    out = repo / "atlas/stores/snapshots"
    monkeypatch.setattr(exporter, "commit_sha", lambda root: "a" * 40)
    monkeypatch.setattr(exporter, "head_blobs", lambda root: {
        rel: exporter.git_blob_sha((root / rel).read_bytes())
        for rel in exporter.node_universe(root) if (root / rel).is_file()
    })
    first = exporter.export(repo, out, full=True)
    # Git is the fixture seam; parent validation and row reuse remain the real code.
    real_run_git = exporter.run_git
    monkeypatch.setattr(exporter, "run_git", lambda root, args, timeout:
        "\0".join(p.relative_to(repo).as_posix() for p in first["path"].iterdir()) + "\0"
        if args == ["ls-files", "-z"] else real_run_git(root, args, timeout))
    real_run = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda args, **kw:
        subprocess.CompletedProcess(args, 0, b"", b"") if args[:3] == ["git", "merge-base", "--is-ancestor"]
        else real_run(args, **kw))
    monkeypatch.setattr(exporter, "diff_paths", lambda *args: {})
    return repo, out, first


def test_empty_diff_carries_verified_rows_without_source_reads(incremental_repo, monkeypatch):
    repo, out, first = incremental_repo
    def no_read(*args, **kwargs):
        pytest.fail("unchanged node was rehashed")
    monkeypatch.setattr(exporter, "node_record", no_read)
    second = exporter.export(repo, out)
    assert (first["path"] / "nodes.jsonl").read_bytes() == (second["path"] / "nodes.jsonl").read_bytes()
    assert second["manifest"]["parent_snapshot"] == first["snapshot_id"]
    assert second["seal_report"]["declaration_heads_read"] == 0
    assert second["manifest"]["diff_counts"] == dict(added=0, modified=0, deleted=0, seal_affected=0)
    assert not (second["path"] / "blobs").exists()
    from atlas.snapshot import load_snapshot
    load_snapshot(second["path"]).verify(check_blob_bytes=False)


def test_changed_added_deleted_equal_full_and_hash_only_delta(incremental_repo, monkeypatch):
    repo, out, first = incremental_repo
    (repo / "edit.md").write_text("After.\n")
    (repo / "added.md").write_text("New.\n")
    (repo / "drop.md").unlink()
    monkeypatch.setattr(exporter, "diff_paths", lambda *args: {
        "edit.md": "M", "added.md": "A", "drop.md": "D"})
    real_record, called = exporter.node_record, []
    def record(root, rel, declared=frozenset()):
        called.append(rel)
        return real_record(root, rel, declared)
    monkeypatch.setattr(exporter, "node_record", record)
    incremental = exporter.export(repo, out)
    assert called == ["added.md", "edit.md"]
    assert "drop.md" not in _rows(incremental["path"])
    assert incremental["manifest"]["parent_snapshot"] == first["snapshot_id"]
    assert incremental["manifest"]["diff_counts"] == dict(added=1, modified=1, deleted=1, seal_affected=0)
    full = exporter.export(repo, out, full=True)
    assert (incremental["path"] / "nodes.jsonl").read_bytes() == (full["path"] / "nodes.jsonl").read_bytes()


def test_parent_tampered_nodes_refuse_before_read_or_write(incremental_repo):
    repo, out, first = incremental_repo
    path = first["path"] / "nodes.jsonl"
    path.write_bytes(path.read_bytes() + b"\n")
    before = set(out.iterdir())
    with pytest.raises(exporter.ExportRefusal, match="PARENT-SIDECAR-HASH-MISMATCH"):
        exporter.export(repo, out)
    assert before == set(out.iterdir())


def test_changed_declaration_seals_unchanged_rendering(incremental_repo, monkeypatch):
    repo, out, _ = incremental_repo
    (repo / "edit.pdf").write_bytes(b"rendered document")
    first = exporter.export(repo, out, full=True)
    monkeypatch.setattr(exporter, "run_git", lambda root, args, timeout:
        "\0".join(p.relative_to(repo).as_posix() for p in first["path"].iterdir()) + "\0")
    (repo / "edit.md").write_text("NEVER-PUBLIC - engine-repo only. Must never travel.\n")
    monkeypatch.setattr(exporter, "diff_paths", lambda *args: {"edit.md": "M"})
    changed = exporter.export(repo, out)
    assert _rows(changed["path"])["edit.pdf"]["sealed"]
    full = exporter.export(repo, out, full=True)
    assert (changed["path"] / "nodes.jsonl").read_bytes() == (full["path"] / "nodes.jsonl").read_bytes()


def test_incremental_symlink_into_sealed_source_refuses_before_scan(incremental_repo, monkeypatch):
    repo, out, _ = incremental_repo
    (repo / "soul").mkdir()
    (repo / "soul/private.md").write_text("sealed source")
    (repo / "alias.md").symlink_to("soul/private.md")
    monkeypatch.setattr(exporter, "diff_paths", lambda *args: {"alias.md": "A"})
    monkeypatch.setattr(exporter, "scan_declarations", lambda *args:
                        pytest.fail("aliased sealed bytes reached the scan"))
    with pytest.raises(exporter.ExportRefusal, match="ALIASED-PATH-REQUIRES-FULL"):
        exporter.export(repo, out)


@pytest.mark.parametrize("status", ["M", "D"])
def test_dirty_sealed_change_or_deletion_refuses_clean_bundle(incremental_repo, monkeypatch, status):
    repo, out, _ = incremental_repo
    (repo / ".git").mkdir()
    monkeypatch.setattr(exporter, "working_delta", lambda root: {"soul/private.md": status})
    with pytest.raises(exporter.ExportRefusal, match="working tree is dirty"):
        exporter.export(repo, out)
