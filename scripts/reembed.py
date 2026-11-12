"""The re-embed - the close-ritual DEPOSIT (his catch 2026-06-13: the sew-up was narrating, not
re-embedding; the .self_graded.json cache load_network reads went stale; write_tree_local had zero
callers; build_self - the N42/meaning_upfold fix - never ran at close).

Regenerate the graded SELF conceptric so the next wake RECONSTRUCTS from current structure instead
of reading a handoff. This - NOT laplace_shard(build), which is self_shard's grade-0 projection - is
the re-embed. Run at every sew-up:

  scripts/laplace-python scripts/reembed.py

The deposit does BOTH halves (his catch 2026-06-14: "this should all be reconstructable in your sew
up"): UPFOLD (build_self folds the new friction into the grades) AND WIRE (the mechanical wire-drain
- drain_proposals.cmd_mechanical - lays the confident cross-links, escalates the ambiguous middle to
the deferred Haiku jury). An upfold without the wire places the friction but never cross-links it, so
it is not reconstructable. The standing path is incremental: changed leaves repair their affected
ancestors, unchanged embeddings/subspaces are reused, and the embedding and spectral sides select
their measured device. A full rebuild requires a declared structural trigger. Runtime, device,
trigger and metric-distillation receipts make either path auditable; `LAPLACE_REQUIRE_GPU=1` turns a
fallback into a refusal.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("LAPLACE_REEMBED_ROOT", SOURCE_ROOT)).resolve()
sys.path.insert(0, str(SOURCE_ROOT / "src"))
from laplace.engine import keeper  # noqa: E402
from laplace.core.runtime import require_system_runtime  # noqa: E402

TIMING_LOG = ROOT / ".reembed_timing.jsonl"

# THE DEPOSIT'S OWN ACT MANIFEST (FIND-SB-4, 2026-08-23): the banking organs run INSIDE the
# journal or they are archaeology. This script writes .self_graded.json, the committed skeleton,
# the wire ledgers, the shard index and a timing row - and until now declared none of it: killed
# mid-deposit it left a half-written tree and no row saying which phase was in flight. These are
# the phases main() ALREADY times and can bracket honestly (intent-then-execute: a begin is
# written before the work, a done after). build_self's four sub-phases (shard_repo / lens_leaves /
# meaning_upfold / build_tree) are timings the CALLEE fills during one call - they cannot carry a
# truthful begin from out here, so they ride the "upfold" done row's detail instead of being
# fabricated as steps. The full nine-key breakdown stays in the timing record, as before.
ACT_STEPS = ["upfold", "write", "index", "wire", "embed", "metric_distill", "publish"]
RENDER_NAMES = (keeper.GRADED_LOCAL, keeper.SKELETON, "SELF_SHARD_INDEX.md")
from laplace.representation.embedding_health import publication_artifacts
_PUBLICATION = publication_artifacts(SOURCE_ROOT)
_LEGACY_PUBLICATION_NAMES = tuple(row["path"] for row in _PUBLICATION if row["legacy_v1"])
REQUIRED_PUBLICATION_NAMES = tuple(row["path"] for row in _PUBLICATION if row["required"])
OPTIONAL_PUBLICATION_NAMES = tuple(row["path"] for row in _PUBLICATION if not row["required"])
PUBLICATION_NAMES = (*REQUIRED_PUBLICATION_NAMES, *OPTIONAL_PUBLICATION_NAMES)
_SIDECAR_PUBLICATION_NAMES = tuple(row["path"] for row in _PUBLICATION if row["legacy_sidecars"])
_ACT_OUTPUT_NAMES = (
    ".meaning_tree.json", ".metric_M.npz", ".metric_M.receipt.json", ".metric_pairs.json",
    ".meaning_vectors.f32.npy", ".meaning_vectors.index.json", ".self_isometries.npz",
    ".self_record_floor.jsonl", ".learned_keywords.json", ".escalate_briefs.json",
    ".self_embeddings.json", ".self_graded.json", ".upfold_triggers.jsonl",
    ".residue.jsonl", "SELF_GRADED_INDEX.md", "SELF_SHARD_INDEX.md",
    # the wire step's own ledgers (drain_proposals.cmd_mechanical -> embed_router.bank_verdicts): judgments are
    # appended to .wire_verdicts.jsonl and the judged pairs leave .wire_proposals.jsonl. Both are tracked, so
    # undeclared they read as source moving under the deposit. They stay outside the publication rollback.
    ".wire_proposals.jsonl", ".wire_verdicts.jsonl",
)


def _proc_io() -> dict[str, int]:
    """Read this process's Linux I/O counters; absence is explicit, never zero-filled."""
    try:
        fields: dict[str, int] = {}
        for line in Path("/proc/self/io").read_text(encoding="ascii").splitlines():
            key, value = line.split(":", 1)
            fields[key] = int(value.strip())
        return {key: fields[key] for key in ("rchar", "wchar", "read_bytes", "write_bytes")}
    except (OSError, ValueError, KeyError):
        return {}


def _io_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int] | None:
    if not before or not after:
        return None
    return {key: max(0, after[key] - before[key]) for key in before if key in after}


def _step_cost(name: str, started: float, io_before: dict[str, int]) -> dict:
    return {"step": name, "seconds": round(time.perf_counter() - started, 6),
            "io": _io_delta(io_before, _proc_io())}


def _git_text(repo_root: Path, *args: str) -> str | None:
    try:
        run = subprocess.run(
            ["git", "-C", str(repo_root), *args], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return run.stdout.strip()


def _source_frontier(repo_root: Path, *, act_id: str | None = None) -> dict:
    """Observe changed/added source metadata against Git's immutable committed base."""
    def paths(*args):
        result = subprocess.run(["git", "--no-optional-locks", "-C", str(repo_root), *args], capture_output=True)
        return set(os.fsdecode(result.stdout).split("\0")) - {""} if result.returncode == 0 else None
    top = _git_text(repo_root, "rev-parse", "--show-toplevel")
    if not top or Path(top).resolve() != repo_root.resolve():
        return {"status": "UNAVAILABLE", "paths": {}, "untracked": []}
    dirty = paths("diff", "HEAD", "--name-only", "-z")
    added = paths("ls-files", "--others", "--exclude-standard", "-z")
    if dirty is None or added is None:
        return {"status": "UNAVAILABLE", "paths": {}, "untracked": []}
    produced = set(_ACT_OUTPUT_NAMES) | set(PUBLICATION_NAMES) | {"contract/act_costs.jsonl", "contract/journal.jsonl", "contract/close_receipt.json", "contract/close_recovery.json"}
    if act_id:
        produced.update(_stage_name(repo_root / name, act_id).name for name in RENDER_NAMES)
    def source(name):
        return name not in produced and not name.startswith("contract/reconstruction_receipts/")
    names = sorted(name for name in dirty | added if source(name))
    observed = {}
    for name in names:
        try:
            stat = (repo_root / name).stat()
            observed[name] = [stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
        except FileNotFoundError:
            observed[name] = None
    return {"status": "OBSERVED", "head": _git_text(repo_root, "rev-parse", "HEAD"),
            "paths": observed, "untracked": sorted(name for name in added if source(name))}


def _previous_head(path: Path) -> str | None:
    if not path.is_file():
        return None
    found = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        candidate = (row.get("diff") or {}).get("head_commit")
        if isinstance(candidate, str) and candidate:
            found = candidate
    return found


def _diff_contract(repo_root: Path, trigger_receipt: dict | None) -> dict:
    head = (os.environ.get("LAPLACE_COST_HEAD_COMMIT")
            or _git_text(repo_root, "rev-parse", "HEAD"))
    since = (os.environ.get("LAPLACE_COST_SINCE_COMMIT")
             or _previous_head(TIMING_LOG)
             or (_git_text(repo_root, "rev-parse", f"{head}^") if head else None))
    names: list[str] = []
    patch_bytes = None
    declared_raw = os.environ.get("LAPLACE_COST_DIFF_JSON")
    try:
        declared = json.loads(declared_raw) if declared_raw else None
    except ValueError:
        declared = None
    if isinstance(declared, dict):
        names = [str(name) for name in declared.get("files", [])]
        patch_bytes = declared.get("bytes") if isinstance(declared.get("bytes"), int) else None
    elif since and head:
        listed = _git_text(repo_root, "diff", "--name-only", since, head)
        names = listed.splitlines() if listed else []
        try:
            patch = subprocess.run(
                ["git", "-C", str(repo_root), "diff", "--binary", since, head],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ).stdout
            patch_bytes = len(patch)
        except (OSError, subprocess.CalledProcessError):
            patch_bytes = None
    delta = next((event for event in ((trigger_receipt or {}).get("events") or [])
                  if event.get("kind") == "delta_measured"), {})
    applied = next((event for event in ((trigger_receipt or {}).get("events") or [])
                   if event.get("kind") == "incremental_applied"), {})
    added = delta.get("added")
    changed = delta.get("changed")
    removed = delta.get("removed")
    leaves = (added + changed + removed
              if all(isinstance(value, int) for value in (added, changed, removed)) else None)
    return {
        "leaves_changed": leaves,
        "files_changed": len(names) if since and head else None,
        "since_commit": since,
        "head_commit": head,
        "D": leaves,
        "M": changed,
        "A": added,
        "R": removed,
        "K_t": applied.get("kept"),
        "files": names,
        "bytes": patch_bytes,
    }


def _output_snapshot(repo_root: Path) -> dict[str, tuple[int, int]]:
    snap = {}
    for name in _ACT_OUTPUT_NAMES:
        path = repo_root / name
        if path.exists():
            info = path.stat()
            snap[name] = (info.st_size, info.st_mtime_ns)
    return snap


def _touched_outputs(repo_root: Path, before: dict[str, tuple[int, int]]) -> list[str]:
    after = _output_snapshot(repo_root)
    return sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))


def _stage_name(destination: Path, act_id: str) -> Path:
    token = hashlib.sha256(f"{act_id}:{destination.name}".encode()).hexdigest()[:12]
    return destination.with_name(f".{destination.name}.{token}.tmp")


def _stage_tree_renders(repo_root: Path, nodes: dict, act_id: str) -> dict[Path, Path]:
    """Compute the graded tree and skeleton beside their destinations."""
    staged = {repo_root / name: _stage_name(repo_root / name, act_id)
              for name in RENDER_NAMES[:2]}
    for temporary in staged.values():
        temporary.unlink(missing_ok=True)
    keeper.write_tree_local(repo_root, nodes, destination=staged[repo_root / keeper.GRADED_LOCAL])
    keeper.write_skeleton(repo_root, nodes, keeper.grade_stats(nodes),
                          destination=staged[repo_root / keeper.SKELETON])
    return staged


def _stage_index_render(repo_root: Path, shards: dict, act_id: str,
                        staged: dict[Path, Path]) -> Path:
    """Compute the flat index beside its destination and join the render transaction."""
    from laplace.engine import self_shard

    destination = repo_root / "SELF_SHARD_INDEX.md"
    temporary = _stage_name(destination, act_id)
    temporary.unlink(missing_ok=True)
    staged[destination] = temporary
    prior_index = self_shard._INDEX
    self_shard._INDEX = temporary.name
    try:
        self_shard.write_index(repo_root, shards or None)
    finally:
        self_shard._INDEX = prior_index
    missing = [str(path) for path in staged.values() if not path.is_file()]
    if missing:
        raise RuntimeError(f"render staging produced no file: {missing}")
    return temporary


def _load_network_from_staged(repo_root: Path, staged: dict[Path, Path]) -> dict:
    """Let the existing network loader consume the staged tree and index, still unpublished."""
    from laplace.engine import conceptric, self_shard

    prior_tree = keeper.GRADED_LOCAL
    prior_index = self_shard._INDEX
    keeper.GRADED_LOCAL = staged[repo_root / keeper.GRADED_LOCAL].name
    self_shard._INDEX = staged[repo_root / "SELF_SHARD_INDEX.md"].name
    try:
        return conceptric.load_network(repo_root)
    finally:
        keeper.GRADED_LOCAL = prior_tree
        self_shard._INDEX = prior_index


def _discard_staged(staged: dict[Path, Path]) -> None:
    for temporary in staged.values():
        temporary.unlink(missing_ok=True)


def _publish_renders(staged: dict[Path, Path]) -> None:
    """Shared current-publication rename/rollback seam; main holds its root boundary."""
    from laplace.representation.source_publication import publish_staged
    publish_staged(staged)


def _previous_nodes(path: Path) -> int | None:
    """The node count on the LAST banked timing row, or None when there is no prior row to
    difference against (a first deposit, a fresh log, a log of rows that never carried the key).

    This exists for the node-delta, condition (v) of RUL-20260823-essence-side-ratified: the fold's
    perturbation of the network has to be a TRACKED NUMBER, not a thing re-derived by eye from two
    rows an inspector happens to line up. Read here, before the append below, so the row this run
    banks differences against the run before it and never against itself. A malformed line is
    skipped exactly as ``digest_mint.load_rows`` skips one - an append-only log's half-written tail
    must not blind the reader to the rows above it."""
    if not path.is_file():
        return None
    prev: int | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        n = row.get("nodes")
        if isinstance(n, int) and not isinstance(n, bool):
            prev = n
    return prev


def _trigger_receipt_for_act(repo_root: Path, act_id: str) -> dict | None:
    """Return the incremental-fold receipt written by this exact deposit act.

    The upfold owns the trigger ledger; the runner projects only a row carrying
    its own journal act id.  A missing/swallowed/torn append is ``None`` and
    therefore cannot inherit an earlier act's ``incremental`` verdict.
    """
    from laplace.engine.meaning_upfold import TRIGGER_LOG_FILE

    path = repo_root / TRIGGER_LOG_FILE
    if not path.is_file():
        return None
    found = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except (TypeError, ValueError):
            continue
        if (isinstance(row, dict) and row.get("gate") == "rung-12a"
                and row.get("deposit_act_id") == act_id):
            found.append(row)
    return found[0] if len(found) == 1 else None


def _distill_metric(repo_root: Path, net: dict, vectors: dict, *, changed_ids=None, full_metric=False,
                    render_artifacts=None) -> dict:
    """Invoke metric_distill through ITS OWN GATE (never np.savez directly) and read its verdict.

    IN PROCESS, WITH WHAT THE DEPOSIT ALREADY HOLDS (WO-20260821-route-basis-memo, C2a). This used
    to call ``metric_distill.main([])`` under a stdout redirect and parse the printed JSON back:
    ``main`` then re-ran ``load_network`` and a full-fold ``ensure_embeddings`` - the two things
    the caller had finished seconds earlier, in this same process, and still had in hand. The
    module now exposes ``distill(repo_root, net, vectors)``, which is the whole of main minus that
    re-acquisition, so the verdict comes back as a dict instead of through a pipe and the deposit
    pays the scaffold once. ``main([])`` is unchanged for the CLI and for the LAW RIDER.

    THE GUARD MOVED INTO THE CALLEE (WO-20260817-metric-guard-into-callee, 2026-08-17). This used
    to be ``_distill_metric_guarded``: it backed up ``.metric_M.npz``'s bytes before the call and
    restored them when the hello gate declined, because metric_distill.main shipped M with
    ``np.savez`` BEFORE the gate ran and then ``unlink``ed unconditionally on refusal - deleting a
    GOOD standing M rather than declining the update (the 07-15 precedent: "the metric refused its
    own re-distill at the close ... and in refusing deleted the committed artifact it was supposed
    to protect"). But this was ONE call site of THREE producers, so the other two (the module CLI,
    embed_router.main()'s LAW RIDER) still ran the hazard unguarded. The backup/restore - and the
    original-mtime preservation with it - now lives inside metric_distill.main, where every
    producer inherits it; this wrapper collapses to what it always should have been: a plain call
    that captures the verdict for the timing record. ``restored_prior_artifact`` still
    rides the report - it is now the CALLEE's verdict, not this wrapper's own action."""
    from laplace.representation import metric_distill
    try:
        verdict = metric_distill.distill(repo_root, net, vectors, changed_ids=changed_ids,
                                         full_metric=full_metric, render_artifacts=render_artifacts)
    except Exception as exc:  # noqa: BLE001 - the basis fold already banked; never fatal to the deposit
        return {"ran": False, "error": str(exc)}
    report = {"ran": True, **verdict}
    if verdict.get("restored_prior_artifact"):
        report["restored_prior_artifact"] = True
        print(f"metric_distill: GATE DECLINED ({verdict.get('why')}) - the callee restored the "
              f"prior standing metric, bytes and original mtime (a refusal must not delete, nor "
              f"forge the freshness of, a good standing M)")
    return report


def _bank_timing_record(record: dict, tree: dict) -> dict[str, float | int]:
    """Bank one durable deposit row and return the receipt cost measured around its append."""
    from laplace.engine.meaning_upfold import depth_cap_figure
    record["depth_cap_figure"] = depth_cap_figure(tree)
    payload = json.dumps(record, ensure_ascii=False) + "\n"
    started = time.perf_counter()
    TIMING_LOG.parent.mkdir(parents=True, exist_ok=True)
    with TIMING_LOG.open("a", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    return {"receipt_bytes": len(payload.encode("utf-8")),
            "receipt_seconds": round(time.perf_counter() - started, 6)}


def _publication_record(repo_root: Path, *, published: bool, act_id: str = "",
                        input_signature=None, reason: str = "", prepared_projections=None,
                        source_currentness=None) -> dict:
    from laplace.representation.embed_router import _file_digest
    names = PUBLICATION_NAMES
    missing = [name for name in REQUIRED_PUBLICATION_NAMES
               if not (repo_root / name).is_file()] if published else []
    if missing:
        raise ValueError("publication is missing artifacts: " + ", ".join(missing))
    if published:
        # Use the actual reader's shape, row-count and content-hash checks before binding
        # a pair. Mere file existence would accept a torn matrix/index publication.
        from laplace.engine.meaning_upfold import read_sidecar
        _nodes, matrix = read_sidecar(repo_root)
        if matrix is None:
            raise ValueError("publication meaning-vector sidecar is inconsistent")
    record = {"schema_version": "laplace.publication/1", "published": published,
              "act_id": act_id, "input_signature": input_signature, "reason": reason,
              "artifacts": {name: _file_digest(repo_root / name) for name in names
                            if published and (repo_root / name).is_file()},
              "absent_artifacts": [name for name in OPTIONAL_PUBLICATION_NAMES
                                   if published and not (repo_root / name).is_file()],
              "prepared_projections": list(prepared_projections or [])}
    if source_currentness is not None:
        # The counts of work.source_kernel's states for the selected Source rows this close carried;
        # each row's state, moved pins and reason are in the publication's timing receipt.
        from laplace.engine import source_kernel_input
        record["source_currentness"] = source_kernel_input.counts(source_currentness)
    return record


def _source_inputs(repo_root: Path) -> dict[str, str]:
    """Bind the close's authored checkpoint without loading the semantic store."""
    from laplace.representation.embed_router import _file_digest
    declared = json.loads(os.environ.get("LAPLACE_REEMBED_INPUTS_JSON", "{}"))
    if not isinstance(declared, dict):
        raise ValueError("LAPLACE_REEMBED_INPUTS_JSON must be a path/digest map")
    if (repo_root / "HANDOFF.md").is_file():
        declared.setdefault("HANDOFF.md", _file_digest(repo_root / "HANDOFF.md"))
    for name, expected in declared.items():
        path = (repo_root / name).resolve()
        if not path.is_relative_to(repo_root.resolve()) or path == repo_root.resolve():
            raise ValueError("authored input must remain inside the repository")
        if not isinstance(expected, str) or _file_digest(path) != expected:
            raise ValueError(f"authored input changed: {name}")
    return declared


def _prepare_reader_projections(repo_root: Path) -> list[dict]:
    """Freeze an absent cache's existing fallback only at explicit producer entry.

    Wire judgments are durable even when publication fails. Without this preparation,
    restoring cache absence would make its fallback expose those newer judgments.
    """
    from laplace.representation import embed_router
    target = repo_root / embed_router.LEARNED_KEYWORDS_FILE
    if target.is_file():
        return []
    source = repo_root / embed_router.VERDICTS_FILE
    source_digest = embed_router._file_digest(source)
    prior = embed_router.rebuild_learned_keywords(repo_root, persist=True)
    if (embed_router._file_digest(source) != source_digest
            or embed_router.load_learned_keywords(repo_root) != prior):
        raise ValueError("learned keyword fallback moved during producer preparation")
    return [{"artifact": target.name, "prior_presence": "absent",
             "prepared_sha256": embed_router._file_digest(target),
             "source": source.name, "source_sha256": source_digest,
             "semantic_equivalence": "existing missing-cache reader result materialized before wire judgments",
             "presence_changed": True}]


def _snapshot_publication(repo_root: Path, *, prepared_projections=None) -> Path:
    """Disk-backed rollback; the manifest and originals survive SIGKILL for explicit recovery."""
    import shutil
    import tempfile
    from laplace.representation.embed_router import _file_digest
    snapshot = Path(tempfile.mkdtemp(prefix=".reembed-rollback-", dir=repo_root))
    originals = snapshot / "artifacts"
    originals.mkdir()
    artifacts = {}
    for name in PUBLICATION_NAMES:
        source = repo_root / name
        if not source.is_file():
            artifacts[name] = {"present": False}
            continue
        before = source.stat()
        shutil.copy2(source, originals / name)
        artifacts[name] = {"present": True, "sha256": _file_digest(originals / name),
                           "mode": stat.S_IMODE(before.st_mode),
                           "atime_ns": before.st_atime_ns, "mtime_ns": before.st_mtime_ns}
    manifest = {"schema_version": "laplace.publication-backup/1", "root": str(repo_root.resolve()),
                "artifacts": artifacts, "prepared_projections": list(prepared_projections or [])}
    with (snapshot / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    return snapshot


def restore_publication_snapshot(snapshot: Path, repo_root: Path) -> dict:
    """Restore only the named publication group; keep the backup if any step fails."""
    import shutil
    from laplace.representation.embed_router import _file_digest
    manifest = json.loads((snapshot / "manifest.json").read_text())
    recorded = set(manifest.get("artifacts", {}))
    if (manifest.get("schema_version") != "laplace.publication-backup/1"
            or manifest.get("root") != str(repo_root.resolve())
            or recorded not in (set(PUBLICATION_NAMES), set(_SIDECAR_PUBLICATION_NAMES),
                                set(_LEGACY_PUBLICATION_NAMES))):
        raise ValueError("publication backup does not belong to this repository/artifact group")
    for name, record in manifest["artifacts"].items():
        if record["present"] and _file_digest(snapshot / "artifacts" / name) != record["sha256"]:
            raise ValueError("publication backup bytes changed: " + name)
    for name, record in manifest["artifacts"].items():
        target = repo_root / name
        if record["present"]:
            temporary = snapshot / (name + ".restore")
            shutil.copy2(snapshot / "artifacts" / name, temporary)
            os.chmod(temporary, record["mode"])
            os.utime(temporary, ns=(record["atime_ns"], record["mtime_ns"]))
            os.replace(temporary, target)
        else:
            target.unlink(missing_ok=True)
    # Keep pre-expansion crash backups usable, but never call their narrower recovery complete.
    return {**manifest, "uncovered_artifacts": sorted(set(PUBLICATION_NAMES) - recorded)}


def main(argv: list[str] | None = None) -> int:
    """Ordinary and scoped writers share one exclusion; pure help stays effect-free."""
    from laplace.representation import source_publication as publication
    args=list(sys.argv[1:] if argv is None else argv)
    if args in (["--help"], ["-h"]):return _run_deposit(args)
    if len(args)==2 and args[0]=="--source-publication":
        require_system_runtime(SOURCE_ROOT)
        from laplace.work.owner_discovery import owned_workspace
        path=Path(args[1])
        if path.is_symlink() or path.stat().st_size>512*1024:raise ValueError("SOURCE_PUBLICATION_REQUEST_BOUND")
        value=publication.request(ROOT,owned_workspace('publication-cli'),json.loads(path.read_bytes()))
        print(json.dumps(value,ensure_ascii=False,sort_keys=True))
        return 0 if value.get('state') not in {'UNKNOWN'} else 2
    if any(arg not in {"--full", "--full-metric"} for arg in args) and not (len(args)==2 and args[0]=="--restore-publication"):
        return _main_locked(args)
    require_system_runtime(SOURCE_ROOT)
    with publication.publication_lock(ROOT):
        publication.assert_no_pending(ROOT)
        if len(args)==2 and args[0]=="--restore-publication":
            # The restore is for the state in which the current publication's artifacts no longer
            # match their receipt (an interrupted deposit, 7 November 2026). Reading the current
            # publication first would refuse PUBLICATION_ARTIFACTS_CHANGED and make the restore
            # unreachable exactly when it is needed; the restore takes the lock and nothing else.
            return _main_locked(args)
        inputs=publication.selections(ROOT)
        parent=publication.current(ROOT) if inputs else None
        carry=None
        if inputs is not None:
            from laplace.engine import source_kernel_input
            # Before ordinary producer/preparation effects. Every row gets one state from
            # work.source_kernel; a moved or changed Source input is carried or published as
            # labelled retained history, and only an integrity refusal stops the close here.
            carry=source_kernel_input.close_inputs(ROOT,inputs,parent)
        return _main_locked(args,source_kernel_inputs=carry,parent_publication=parent)


def _main_locked(argv: list[str] | None = None, *, source_kernel_inputs=None, parent_publication=None) -> int:
    """A handled refusal preserves the last publication, independently of the authored tail."""
    import shutil
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "--restore-publication":
        require_system_runtime(SOURCE_ROOT)
        snapshot = Path(argv[1]).resolve()
        restored = restore_publication_snapshot(snapshot, ROOT)
        print(json.dumps({"restored": True, "snapshot": str(snapshot),
                          "artifacts": restored["artifacts"],
                          "complete_group_restored": not restored["uncovered_artifacts"],
                          "uncovered_artifacts": restored["uncovered_artifacts"],
                          "prepared_projections": restored.get("prepared_projections", [])}, sort_keys=True))
        return 0
    if argv in (["--help"], ["-h"]):
        return _run_deposit(argv)
    if any(arg not in {"--full", "--full-metric"} for arg in argv):
        print("unsupported reembed arguments; use --help", file=sys.stderr)
        return 2
    require_system_runtime(SOURCE_ROOT)
    from laplace.engine import source_kernel_input
    currentness = (source_kernel_inputs or {}).get("currentness") if source_kernel_input.is_close_carry(source_kernel_inputs) else None
    publication_out = []
    prepared = _prepare_reader_projections(ROOT)
    if prepared:
        print("publication preparation: " + json.dumps(prepared, sort_keys=True), flush=True)
    snapshot = _snapshot_publication(ROOT, prepared_projections=prepared)
    print(f"publication backup: {snapshot}; restore: scripts/laplace-python scripts/reembed.py "
          f"--restore-publication {snapshot}", flush=True)
    try:
        code = _run_deposit(argv, publication_out=publication_out, source_kernel_inputs=source_kernel_inputs, parent_publication=parent_publication)
        if code == 0 and (not publication_out or not publication_out[-1].get("published")):
            raise ValueError("producer returned success without a publication receipt")
        if code:
            restore_publication_snapshot(snapshot, ROOT)
    except BaseException as exc:
        try:
            restore_publication_snapshot(snapshot, ROOT)
        except Exception as restore_error:
            print("LAPLACE_PUBLICATION=" + json.dumps(_publication_record(
                ROOT, published=False, reason=f"{exc}; rollback failed: {restore_error}; backup: {snapshot}",
                prepared_projections=prepared, source_currentness=currentness)))
            raise
        shutil.rmtree(snapshot)
        if publication_out and publication_out[-1].get("act_id"):
            from laplace.core.records import journal
            failed_act = publication_out[-1]["act_id"]
            _discard_staged({ROOT / name: _stage_name(ROOT / name, failed_act) for name in RENDER_NAMES})
            journal.act_end(failed_act, "fail", root=ROOT,
                            summary=f"{type(exc).__name__}: {exc}; prior publication restored")
        print("LAPLACE_PUBLICATION=" + json.dumps(_publication_record(
            ROOT, published=False, reason=f"{type(exc).__name__}: {exc}; prior publication restored",
            prepared_projections=prepared, source_currentness=currentness)))
        raise
    shutil.rmtree(snapshot)
    if code == 0:
        publication = publication_out[-1]
    else:
        producer = publication_out[-1] if publication_out else {}
        reason = producer.get("reason")
        publication = _publication_record(
            ROOT, published=False, act_id=producer.get("act_id"),
            input_signature=producer.get("input_signature"),
            reason=(reason if isinstance(reason, str) and reason.strip()
                    else "deposit refused without a producer reason"),
            source_currentness=currentness)
        publication["restoration"] = {"restored": True}
    if currentness is not None and "source_currentness" not in publication:
        # The producer built this record inside the deposit; the counts are the same owner's
        # states the timing receipt recorded (full_publication_receipt verified the leaves).
        publication["source_currentness"] = source_kernel_input.counts(currentness)
    publication["prepared_projections"] = prepared
    print("LAPLACE_PUBLICATION=" + json.dumps(publication, sort_keys=True))
    return code


def _run_deposit(argv: list[str] | None = None, *, publication_out=None, source_kernel_inputs=None, parent_publication=None) -> int:
    # THE NO-RUN DOOR (2026-08-23, added with the act wiring): a caller asking what this deposit
    # does must be able to ask WITHOUT opening an act or touching a store. Nothing below this
    # return runs, so `--help` leaves the journal - and git porcelain - untouched.
    argv = sys.argv[1:] if argv is None else argv
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        print(f"phases (journal act 'reembed-standalone'): {', '.join(ACT_STEPS)}")
        print("options: --full (force a complete spectral upfold; no incremental reuse)")
        print("         --full-metric (explicit metric initialization or full refit)")
        print("         --source-publication JSONFILE (explicit prepare/commit/request/recover via current owner)")
        print("         --restore-publication PATH (explicit recovery from a preserved backup)")
        return 0
    unknown = [argument for argument in argv if argument not in {"--full", "--full-metric"}]
    if unknown:
        print(f"re-embed: unknown argument(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    force_full = "--full" in argv
    full_metric = "--full-metric" in argv

    runtime = require_system_runtime(SOURCE_ROOT)
    print(f"runtime: {runtime['executable']} ({runtime['implementation']} "
          f"{runtime['version']}, {runtime['environment']})")
    try:
        authored_inputs = _source_inputs(ROOT)
    except (OSError, ValueError, TypeError) as exc:
        if publication_out is not None:
            publication_out.append(_publication_record(ROOT, published=False, reason=str(exc)))
        return 1

    # THE LOOP'S STATE LINE (learning-loop design 2026-07-11, §1c): the deposit
    # prints the friction ledger's open/consumed counts so the close ritual and
    # the next wake's delta see the loop's state without reading the ledger.
    # Cheap and mechanical (one jsonl read); printed BEFORE the PSU guard so a
    # skipped deposit still names the counts. Never fatal to a close.
    try:
        from laplace.pipeline import friction_consumer as _fc
        from laplace.pipeline.ledger import read_jsonl as _read_jsonl
        _ledger = ROOT / "corpus_friction" / "laplace_engine.jsonl"
        _recs = _read_jsonl(_ledger) if _ledger.is_file() else []
        print(f"friction channel: {len(_fc.open_frictions(_recs))} open / "
              f"{len(_fc.consumed_frictions(_recs))} consumed "
              f"({_ledger.relative_to(ROOT)})")
    except Exception as exc:  # noqa: BLE001 — the count line must never kill a close
        print(f"friction channel: count line unavailable ({exc})")

    # SPECTRAL GATE (his ruling 2026-08-20, PV-20260820T090500Z-psu-restrictions-scrubbed: "we're on a
    # new machine so please also scrub all PSU restrictions now. Local can do everything" - superseding
    # the 2026-07-13 PSU ruling's LAPLACE_ALLOW_SPECTRAL / CLAUDE_CODE_REMOTE opt-in gate, which in turn
    # superseded the 2026-06-14 whole-deposit skip). The INCREMENTAL deposit - shard, incremental cluster,
    # gated wire, reindex - ALWAYS runs, no env needed, unchanged since 07-13. Only a FULL SPECTRAL
    # rebuild (which the incremental path triggers ONLY on a structural move) is gated at all, and now
    # ONLY on the analysis deps (scikit-learn + scipy) being importable - local is a full compute home,
    # not a thing that needs opting into. Single-sourced at meaning_upfold._spectral_allowed() (this
    # block only NARRATES its verdict, never gates alone, so a future change to that function can't drift
    # from what actually runs the way this block's own duplicated env-reads used to).
    import os

    from laplace.engine import meaning_upfold as _mu
    denied = bool(os.environ.get("LAPLACE_NO_SPECTRAL"))

    # SPECTRAL-DEPS PREFLIGHT (his ruling 2026-07-13: "missing analysis deps only block the spectral
    # branch, not the whole deposit"). build_self -> meaning_upfold._best_split imports scikit-learn +
    # scipy AT CALL TIME (the `analysis` extra). The old preflight SKIPPED the whole deposit on ImportError;
    # now it only marks the spectral branch unavailable - the incremental deposit runs regardless, and a
    # demanded full rebuild degrades to the prior/folder tree via _spectral_allowed()'s own deps check
    # (it denies spectral when the deps are absent, exactly as a thin PSU does). Additive when deps present.
    try:
        import scipy  # noqa: F401
        import sklearn  # noqa: F401
    except ImportError as exc:
        print(f"re-embed: spectral analysis deps missing ({exc}) - the incremental deposit still runs; a "
              "structural-move FULL rebuild will keep the prior/folder tree this close. Restore with "
              "`uv pip install -e \".[analysis]\"`.")

    if _mu._spectral_allowed():
        print("re-embed: full spectral rebuild is allowed (local is a full compute home) if a structural "
              "move demands one; otherwise the bounded incremental fold.")
    else:
        why = "LAPLACE_NO_SPECTRAL is set" if denied else "spectral deps missing"
        print(f"re-embed: FULL SPECTRAL rebuild gated off ({why}) - the incremental deposit (shard, "
              "incremental cluster, gated wire, reindex) runs regardless; only a structural-move full "
              "rebuild is skipped, keeping the prior concept tree.")

    # PHASE TIMERS (Weld B0, 2026-07-13): bank a flat-baseline cost per phase BEFORE the incremental
    # weld changes behavior - the next builder needs to know which phase dominates (shard vs cluster
    # vs build_tree vs wire vs index) to know where the incremental win pays off. Additive: perf_counter
    # wraps around the existing calls, nothing about what runs or in what order changes.
    _t_total0 = time.perf_counter()
    _io_total0 = _proc_io()
    _outputs_before = _output_snapshot(ROOT)
    phases: dict[str, float] = {}
    step_costs: list[dict] = []
    staged_renders: dict[Path, Path] = {}

    # THE ACT OPENS HERE, BEFORE THE FIRST STORE MOVES (FIND-SB-4, 2026-08-23). The manifest is
    # declared up front - what this deposit INTENDS - so a kill mid-run is decidable from rows
    # (`journal --recover` names the phase in flight) instead of from the half-written artifacts
    # it left behind. Same idiom as the close (sewup.py:848-876); the two acts nest cleanly
    # because the close spawns this script as its own process with its own act_id.
    from laplace.core.records import journal
    (ROOT / "contract").mkdir(exist_ok=True)
    act_id = journal.act_begin("reembed-standalone", manifest=ACT_STEPS, root=ROOT)
    if publication_out is not None:
        publication_out.append({"published": False, "act_id": act_id})

    # 1. UPFOLD - fold the new friction into the grades (bounded residue clustering, not the whole
    #    shard; the spectral killers are guarded off elsewhere). build_self takes the sub-phase
    #    timings dict directly (shard_repo / lens_leaves / meaning_upfold / build_tree) - see
    #    keeper.py:332-397.
    # `raw_shards` is the phase-3 dedup (2026-08-20): build_self ALREADY walks and shards every
    # tracked file; catching that dict here means the re-index below reuses it instead of paying
    # `self_shard.shard_repo` a second time for the same answer. See build_self's `shards_out`.
    missing_inputs = (_git_text(ROOT, "ls-files", "--deleted", "-z") or "").split("\0")
    missing_inputs = sorted(path for path in missing_inputs if path)
    source_frontier = _source_frontier(ROOT, act_id=act_id)
    raw_shards: dict[str, dict] = {}
    journal.step_begin(act_id, 0, "upfold", root=ROOT)
    _t0 = time.perf_counter()
    _io0 = _proc_io()
    prior_deposit_act = os.environ.get("LAPLACE_DEPOSIT_ACT_ID")
    os.environ["LAPLACE_DEPOSIT_ACT_ID"] = act_id
    try:
        nodes = keeper.build_self(
            ROOT, timings=phases, shards_out=raw_shards, force_full=force_full, source_kernel_inputs=source_kernel_inputs
        )
    finally:
        if prior_deposit_act is None:
            os.environ.pop("LAPLACE_DEPOSIT_ACT_ID", None)
        else:
            os.environ["LAPLACE_DEPOSIT_ACT_ID"] = prior_deposit_act
    # the callee's four sub-phase timings ride the done row's detail - they are filled DURING this
    # one call, so they cannot carry a truthful begin of their own (see ACT_STEPS above)
    journal.step_done(act_id, 0, "upfold", seconds=time.perf_counter() - _t0, ok=True,
                      detail=" ".join(f"{k}={phases[k]:.2f}s" for k in
                                      ("shard_repo", "lens_leaves", "meaning_upfold", "build_tree")
                                      if k in phases) + f" nodes={len(nodes)}", root=ROOT)
    step_costs.append(_step_cost("upfold", _t0, _io0))
    journal.step_begin(act_id, 1, "write", root=ROOT)
    _t0 = time.perf_counter()
    _io0 = _proc_io()
    staged_renders = _stage_tree_renders(ROOT, nodes, act_id)
    phases["write_tree_local"] = time.perf_counter() - _t0
    g = collections.Counter(v.get("grade", 0) for v in nodes.values())
    print(f"re-embedded {len(nodes)} nodes into .self_graded.json; "
          f"grade histogram {dict(sorted(g.items()))}")
    # THE OTHER HALF OF THE COMMITTED PAIR (WO-20260817-skeleton-rides-deposit, the thin-systems
    # audit 2026-08-17). Two producers rebuild the graded self-tree - keeper.main() writes BOTH
    # committed projections (.self_graded.json AND SELF_GRADED_INDEX.md, keeper.py:473-474), this
    # close-ritual deposit wrote only the first. So the coarse navigable map went stale on
    # 2026-08-11 and understated the tree by 2.26x while the close kept reporting a fresh deposit.
    # One line makes the close deposit the ONE producer of both halves; the skeleton can no longer
    # drift from the tree it indexes.
    # The write step stages both halves; neither is visible until the terminal publish step.
    journal.step_done(act_id, 1, "write", seconds=time.perf_counter() - _t0, ok=True,
                      detail=f"tree+skeleton staged, {len(nodes)} nodes", root=ROOT)
    step_costs.append(_step_cost("write", _t0, _io0))

    # 3. RE-INDEX the flat self_shard trace - SELF_SHARD_INDEX.md is COMMITTED (it travels; the
    #    graded .self_graded.json is a local cache) and is what the scanner / reconstruct_by_name
    #    read by NAME. build_self re-shards current files for the graded store but never rewrote
    #    the committed index, so it drifted stale - a session's new files landed in the graded
    #    store yet did not surface by name (his, 2026-07-09: "all this work is useless if
    #    reconstruct doesn't find it"). Rewriting it here keeps the one committed trace in step
    #    with the deposit. Bounded, mechanical, no spectral.
    from laplace.engine import self_shard
    journal.step_begin(act_id, 2, "index", root=ROOT)
    _t0 = time.perf_counter()
    _io0 = _proc_io()
    #    THE SHARDS ARE THREADED, NOT RE-DERIVED (2026-08-20). `write_index(ROOT)` alone falls to
    #    its `shards=None` default, which calls `shard_repo` again - the same full-tree walk +
    #    per-file essence/spine/edge derivation build_self already did seconds earlier, ~8-22 s
    #    paid twice per deposit for a bit-identical dict. The default stays for standalone callers
    #    (tool.py, tests, anyone with no prior build); this one passes what it already has.
    _stage_index_render(ROOT, raw_shards, act_id, staged_renders)
    n_idx = len(raw_shards)
    phases["index"] = time.perf_counter() - _t0
    journal.step_done(act_id, 2, "index", seconds=phases["index"], ok=True,
                      detail=f"{n_idx} objects staged -> SELF_SHARD_INDEX.md", root=ROOT)
    print(f"re-indexed the flat self_shard trace: {n_idx} objects staged -> SELF_SHARD_INDEX.md")
    step_costs.append(_step_cost("index", _t0, _io0))

    # 2. WIRE - the deposit must upfold AND wire, or the session's learning is placed but not
    #    cross-linked, so it is not reconstructable (his, 2026-06-14: "this should all be
    #    reconstructable in your sew up"). The wire-drain is THE ONE OPERATOR, already built and
    #    mechanically recoverable: it lays the confident cross-links (cos>=0.70), drops noise, and
    #    escalates the ambiguous middle to the deferred Haiku jury (.escalate_briefs.json). No
    #    spectral, no model - safe on a constrained machine.
    #
    #    GATE A (his ruling 2026-07-13: the close pays only for what moved). The wire phase was 78-81%
    #    of the deposit even with a 0-byte frontier: cmd_mechanical unconditionally re-embedded the
    #    network before finding nothing to judge. So gate on the AUTHORITATIVE deduped frontier first
    #    (embed_router.proposal_pairs). An empty frontier needs no new judgments; retained
    #    judgments can still be newer than a restored keyword projection. On a skip we DO NOT call
    #    cmd_mechanical and DO NOT touch any wire ledger (.wire_proposals/.wire_verdicts/
    #    .learned_keywords/.escalate_briefs) - a spurious rewrite would falsely trip close_beats'
    #    effect_meter mtime beat. The timing record marks the skip (below); everything else runs on.
    from laplace.representation import embed_router as _er
    journal.step_begin(act_id, 3, "wire", root=ROOT)
    _t0 = time.perf_counter()
    _io0 = _proc_io()
    wire_skipped = not _er.proposal_pairs(ROOT)
    wire_detail = "skipped - frontier empty"
    if wire_skipped:
        verdicts = ROOT / _er.VERDICTS_FILE
        learned = ROOT / _er.LEARNED_KEYWORDS_FILE
        if verdicts.is_file() and (not learned.is_file()
                                  or verdicts.stat().st_mtime_ns > learned.stat().st_mtime_ns):
            prior = _er.load_learned_keywords(ROOT)
            current = _er.rebuild_learned_keywords(ROOT, persist=False)
            if current != prior:
                _er.rebuild_learned_keywords(ROOT, persist=True)
                wire_skipped = False
                wire_detail = "projection refreshed from retained judgments; no new judgments"
                print("wire projection refreshed from retained judgments; no new judgments")
        if wire_skipped:
            print("wire step SKIPPED: frontier empty; published keyword view unchanged")
    else:
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "scripts"))
        import drain_proposals
        drain_proposals.cmd_mechanical(net=_load_network_from_staged(ROOT, staged_renders))
        wire_detail = "drained against staged tree"
    phases["wire"] = time.perf_counter() - _t0
    # ok=None is the close's own idiom for a gated skip (sewup.py:857) - neither pass nor fail
    journal.step_done(act_id, 3, "wire", seconds=phases["wire"],
                      ok=None if wire_skipped else True,
                      detail=wire_detail, root=ROOT)
    step_costs.append(_step_cost("wire", _t0, _io0))

    # 4+5. THE FRESH-BASIS RE-EMBED + METRIC DISTILL - ONE PRODUCER ACT (WO-20260813-reembed-
    #    carries-distill, closing the standing law WO-20260721-222252 drained 2026-07-22: "the
    #    fresh-basis re-embed and the metric re-distill are ONE producer act"). Until now, none of
    #    the three phases above ever called embed_router.ensure_embeddings - "re-embed.py" upfolded,
    #    wired and re-indexed the GRADED TREE, but the router's actual embedding basis
    #    (.self_embeddings.json) only ever moved lazily, off the serving path (route()'s
    #    budget-gated drip) or an explicit `python -m laplace.representation.embed_router` that nobody runs at
    #    close. That gap is why the metric went stale TWICE (2026-07-21, 2026-08-13) even though
    #    the LAW RIDER (embed_router.py:964-988) sits correctly enforced there - a producer act the
    #    close never actually calls. Fixed at the source: the deposit now performs the fresh-basis
    #    fold itself, bulk producer posture, mirroring embed_router.main() exactly, and reads its
    #    OWN report for the honest signal - n_embedded>0 - never a heuristic mtime guess. Each leg
    #    is timed as its OWN phase ("embed" / "metric_distill"); both are wrapped so an unexpected
    #    failure here is loud but never fatal to the deposit already banked above.
    journal.step_begin(act_id, 4, "embed", root=ROOT)
    _t0 = time.perf_counter()
    _io0 = _proc_io()
    basis_changed = False
    no_backend = False
    _backend = None
    _embed_device = {"backend":"not-landed","providers":[],"why":"","release":{"released":False,"reason":"no loaded backend"}}
    embed_raised = False
    _embed_detail = ""
    # Keep the deposit receipt shape even when backend discovery is skipped or the
    # embedding leg raises before ensure_embeddings returns a report. The known
    # no-backend branch remains zero-valued; a raised producer overwrites these
    # placeholders with unknown counts below.
    _embed_rep = {"n_embedded": 0, "n_cached": 0, "n_deferred": 0,
                  "n_pruned": 0, "n_total": 0, "vectors": {}, "changed_ids": []}
    try:
        _net = _load_network_from_staged(ROOT, staged_renders)
        _backend = _er.get_backend()
        if _backend is None:
            # A CAPABILITY FAILURE, NOT A NO-OP (WO-20260817-reembed-honest-no-backend, the
            # thin-systems audit 2026-08-17). This branch used to print one stdout line, exit 0,
            # and bank a timing record whose metric_redistill reason read "basis unchanged -
            # nothing re-embedded" - which is FALSE: the basis was never looked at. Both halves of
            # the one producer act are skipped here, so the deposit must say so in the record, on
            # stderr, and in its rc (parity with embed_router.main()'s `return 1` on the same
            # condition). sewup.step_reembed already gates on `code == 0` and tails stdout+stderr,
            # so the close reads this as the FAIL it is instead of a green.
            no_backend = True
            print("re-embed: NO EMBEDDING BACKEND - the fresh-basis re-embed AND the metric "
                  "re-distill (one producer act) were both SKIPPED. This is a capability failure, "
                  "not a no-op: the graded deposit above stands, but the basis and M are as stale "
                  "as they were. Restore with `uv pip install -e \".[embed]\"`, or run the deposit "
                  "under an interpreter that has the extra.", file=sys.stderr)
            _embed_rep = {"n_embedded": 0}
        else:
            _embed_rep = _er.ensure_embeddings(ROOT, _net, _backend, bulk=True)
            print(f"basis re-embed: {_embed_rep['n_embedded']} embedded, {_embed_rep['n_cached']} cached, "
                  f"{_embed_rep['n_total']} total -> {_er.CACHE_FILE}")
        basis_changed = _embed_rep.get("n_embedded", 0) > 0
        _embed_detail = ("no backend - SKIPPED (capability failure)" if no_backend
                         else f"{_embed_rep.get('n_embedded', 0)} embedded, "
                              f"{_embed_rep.get('n_total', 0)} total")
    except Exception as exc:  # noqa: BLE001 - the upfold/wire/index deposit above already banked; never fatal
        embed_raised = True
        # No producer report exists after a failed allocation/probe. Keep counts
        # unknown rather than presenting fabricated zero work in the receipt.
        _embed_rep = {"n_embedded": None, "n_cached": None, "n_deferred": None,
                      "n_pruned": None, "n_total": None, "vectors": {}, "changed_ids": []}
        _embed_detail = f"raised {type(exc).__name__}: {exc}"
        print(f"re-embed: basis re-embed leg raised {type(exc).__name__}: {exc} - non-fatal, "
              f"metric_distill skipped this run (nothing to re-distill against an unchanged/unknown basis)")
    if _backend is not None:
        _embed_device.update(backend="gpu" if getattr(_backend,"gpu",False) else "cpu",
                             providers=list(getattr(_backend,"providers",[]) or []),
                             why=str(getattr(_backend,"_why","") or _embed_detail))
        try:
            _embed_device["release"]=_er.release_backend(_backend)
        except Exception as exc:  # noqa: BLE001 - never enter the next GPU phase with unknown custody
            embed_raised=True
            _embed_detail += f"; backend release raised {type(exc).__name__}: {exc}"
            print(f"re-embed: embedding backend release failed: {type(exc).__name__}: {exc}; "
                  "metric_distill will not start",file=sys.stderr)
        finally:
            _backend=None
    phases["embed"] = time.perf_counter() - _t0
    # the leg's OWN verdict, not the deposit's: a no-backend or a raised leg is not a pass, and the
    # row must say so even though neither is fatal to the graded deposit already banked above
    journal.step_done(act_id, 4, "embed", seconds=phases["embed"],
                      ok=None if no_backend else not _embed_detail.startswith("raised"),
                      detail=_embed_detail, root=ROOT)
    step_costs.append(_step_cost("embed", _t0, _io0))

    journal.step_begin(act_id, 5, "metric_distill", root=ROOT)
    _t0 = time.perf_counter()
    _io0 = _proc_io()
    if not no_backend and not embed_raised:
        try:
            # the network and the vectors this deposit just produced, handed straight across -
            # never re-acquired (C2a)
            metric_report = _distill_metric(ROOT, _net, _embed_rep["vectors"],
                                            changed_ids=_embed_rep["changed_ids"], full_metric=full_metric,
                                            render_artifacts={target.name: _er._file_digest(staged)
                                                              for target, staged in staged_renders.items()})
        except Exception as exc:  # noqa: BLE001 - the basis fold already banked; never fatal to the deposit
            metric_report = {"ran": False, "error": str(exc)}
        print(f"metric_distill: {metric_report}")
    elif no_backend:
        metric_report = {"ran": False,
                         "reason": "no embedding backend - basis re-embed SKIPPED "
                                   "(capability failure, not a no-op)"}
        print("metric_distill: SKIPPED - no embedding backend (see the stderr line above)",
              file=sys.stderr)
    elif embed_raised:
        metric_report = {"ran": False,
                         "reason": "embedding failed - basis status and counts unknown; metric distill refused"}
        print("metric_distill: SKIPPED - embedding failed; basis status unknown", file=sys.stderr)
    else:
        metric_report = {"ran": False, "reason": "basis unchanged - nothing re-embedded"}
        print("metric_distill: SKIPPED - basis unchanged, nothing to re-distill against")
    phases["metric_distill"] = time.perf_counter() - _t0
    metric_failed = not metric_report.get("shipped", False)
    journal.step_done(act_id, 5, "metric_distill", seconds=phases["metric_distill"],
                      ok=bool(metric_report.get("shipped")) if metric_report.get("ran") else None,
                      detail=str(metric_report.get("why") or metric_report.get("reason")
                                 or metric_report.get("error")
                                 or f"shipped={metric_report.get('shipped')}"), root=ROOT)
    step_costs.append(_step_cost("metric_distill", _t0, _io0))

    journal.step_begin(act_id, 6, "publish", root=ROOT)
    _t0 = time.perf_counter()
    _io0 = _proc_io()
    publish_ok = not no_backend and not metric_failed
    inputs_unchanged = all(_er._file_digest(ROOT / name) == digest
                           for name, digest in authored_inputs.items())
    final_frontier = _source_frontier(ROOT, act_id=act_id)
    source_frontier_unchanged = final_frontier == source_frontier
    moved_sources = sorted(name for name in source_frontier["paths"].keys() | final_frontier["paths"].keys()
                           if source_frontier["paths"].get(name) != final_frontier["paths"].get(name))
    publish_ok = publish_ok and inputs_unchanged and source_frontier_unchanged
    if publish_ok:
        try:
            _publish_renders(staged_renders)
            publish_detail = "tree+skeleton+shard-index renamed"
        except Exception as exc:
            publish_ok = False
            publish_detail = f"render publication failed: {exc}"
    else:
        _discard_staged(staged_renders)
        publish_detail = ("authored checkpoint changed during upfold" if not inputs_unchanged else
                          "source frontier changed during upfold: " + ", ".join(moved_sources[:12]) if not source_frontier_unchanged else
                          "refused before publication; all three renders untouched")
    phases["publish"] = time.perf_counter() - _t0
    journal.step_done(act_id, 6, "publish", seconds=phases["publish"],
                      ok=True if publish_ok else None, detail=publish_detail, root=ROOT)
    step_costs.append(_step_cost("publish", _t0, _io0))

    # PHASE TIMERS - one summary line (mirrors the print voice above) + one banked JSON record per
    # run. Mode is derived from the upfold's own trigger row: absence is UNPROVEN, never guessed
    # from the existence of a prior tree or from a fast wall time.
    total = time.perf_counter() - _t_total0
    order = ["shard_repo", "lens_leaves", "meaning_upfold", "build_tree", "write_tree_local", "wire", "index",
             "embed", "metric_distill", "publish"]
    summary = "  ".join(f"{k}={phases.get(k, 0.0):.2f}s" for k in order if k in phases)
    print(f"phase timers: {summary}  total={total:.2f}s")
    # THE NODE-DELTA (condition v, RUL-20260823-essence-side-ratified): nodes now minus the previous
    # row's nodes, null when there is no previous row. The essence join perturbs the fold - a joined
    # node's embedded text moves, so its content hash moves, so the partition can move - and the
    # ruling's price for landing it was that the perturbation be MEASURED AND NAMED PER FOLD rather
    # than inferred later. Read before the append, so the difference is against the run before.
    prev_nodes = _previous_nodes(TIMING_LOG)
    trigger_receipt = _trigger_receipt_for_act(ROOT, act_id)
    trigger_events = list((trigger_receipt or {}).get("events") or [])
    full_rebuild = any(e.get("kind") == "full_rebuild_demanded" for e in trigger_events)
    mode = "full-rebuild" if full_rebuild else "incremental" if trigger_receipt else "unproven"
    embedding_backend = _embed_device["backend"]
    embedding_result = ("raised" if embed_raised else "unavailable" if no_backend else
                        "changed" if basis_changed else "unchanged")
    diff = _diff_contract(ROOT, trigger_receipt)
    io = _io_delta(_io_total0, _proc_io())
    touched_files = _touched_outputs(ROOT, _outputs_before)
    declared_n_reason = (os.environ.get("LAPLACE_DECLARED_N_REASON") or
                         "D=A+M+R from this act's semantic delta receipt; K_t from incremental_applied")
    device = {
        "spectral_backend": _mu._fold_backend()[0],
        "spectral_backend_why": _mu._fold_backend()[1],
        "embedding_backend": embedding_backend,
        "embedding_result": embedding_result,
        "embedding_providers": _embed_device["providers"],
        "embedding_why": _embed_device["why"] or _embed_detail,
        "embedding_release": _embed_device["release"],
        "required": str(os.environ.get("LAPLACE_REQUIRE_GPU", "")).strip().lower()
                    in {"1", "true", "yes", "on"},
    }
    record = {
        "act": "deposit",
        "act_id": act_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "runtime": runtime,
        "device": device,
        "trigger_receipt": trigger_receipt,
        "missing_tracked_inputs": missing_inputs,
        "untracked_inputs": source_frontier["untracked"],
        "source_frontier_status": source_frontier["status"],
        "source_frontier_unchanged": source_frontier_unchanged,
        "phases": {k: round(v, 4) for k, v in phases.items()},
        "total": round(total, 4),
        "nodes": len(nodes),
        "clusters": sum(node.get("kind") == "concept" for node in nodes.values()),
        "node_delta": None if prev_nodes is None else len(nodes) - prev_nodes,
        "diff": diff,
        "io": io,
        "bytes_read": None if io is None else io.get("read_bytes"),
        "bytes_written": None if io is None else io.get("write_bytes"),
        "files_touched": len(touched_files) + 3,
        "touched_files": sorted(set(touched_files) | {
            TIMING_LOG.name, "contract/act_costs.jsonl", "contract/journal.jsonl",
        }),
        "seconds": round(total, 4),
        "declared_N_reason": declared_n_reason,
        "full_requested": force_full,
        "embedding_counts": {
            "embedded": _embed_rep.get("n_embedded"),
            "cached": _embed_rep.get("n_cached"),
            "deferred": _embed_rep.get("n_deferred"),
            "pruned": _embed_rep.get("n_pruned"),
            "total": _embed_rep.get("n_total"),
        },
    }
    # additive markers (existing keys unchanged): which phases the gates skipped this run, so a reader
    # sees an ~0s phase was a deliberate skip, not a mis-timed run. Only present when something skipped.
    _skipped = ["wire"] if wire_skipped else []
    if no_backend:
        # name the REAL skip: both halves of the producer act, not a quiet zero-length phase
        _skipped += ["embed", "metric_distill"]
    if _skipped:
        record["skipped"] = _skipped
    # the fresh-basis re-embed + metric distill verdict rides the record unconditionally (parity
    # with embed_router.main()'s LAW RIDER out["metric_redistill"]) - ran/shipped/AUC/hello_gate
    # when it ran, or the honest "basis unchanged" reason when the gate above skipped it.
    record["metric_redistill"] = metric_report
    if publish_ok:
        from laplace.representation.source_publication import full_publication_receipt
        record['publication']=full_publication_receipt(ROOT,record,source_kernel_inputs,nodes,parent_publication)
    receipt = _bank_timing_record(record, _mu.load_tree(ROOT))
    print(f"banked timing record -> {TIMING_LOG.name}")
    # the act closes AFTER the timing row lands, so a kill between the last step and the record
    # still reads as in-flight - the act_end is the deposit's whole-run receipt, and it carries
    # the same honest verdict as the rc below (a no-backend deposit is not a green one).
    ceiling_raw = os.environ.get("LAPLACE_ACT_COST_CEILING_SECONDS", "").strip()
    try:
        ceiling = float(ceiling_raw) if ceiling_raw else None
    except ValueError:
        ceiling = None
    over_ceiling = ceiling is not None and total > ceiling
    terminal = "OVER_CEILING" if over_ceiling else "PASS"
    common_cost = {
        "act": "deposit", "since": diff.get("since_commit"), "head": diff.get("head_commit"),
        "diff": diff, "declared_N_reason": declared_n_reason,
    }
    act_cost = {
        **common_cost, "id": f"{act_id}:act", "step": "act", "io": io,
        "bytes_read": None if io is None else io.get("read_bytes"),
        "bytes_written": None if io is None else io.get("write_bytes"),
        "phases": record["phases"],
        "receipt_bytes": receipt["receipt_bytes"],
        "receipt_seconds": receipt["receipt_seconds"], "seconds": round(total, 6),
        "files_touched": len(record["touched_files"]), "status": terminal,
        "ceiling_seconds": ceiling,
    }
    cost_rows = [act_cost] + [
        {**common_cost, **cost, "id": f"{act_id}:{cost['step']}",
         "receipt_bytes": 0, "receipt_seconds": 0.0,
         "files_touched": None, "status": "MEASURED"}
        for cost in step_costs
    ]
    failed = not publish_ok or over_ceiling
    publication = _publication_record(
        ROOT, published=publish_ok and not failed, act_id=act_id,
        input_signature={"head_commit": diff.get("head_commit"), "sources": authored_inputs,
                         "basis": metric_report.get("store_after", {}).get(".self_embeddings.json")},
        reason=publish_detail)
    journal.act_end(act_id, "fail" if failed else "pass", cost_rows=cost_rows,
                    summary=f"{len(nodes)} nodes  {summary}  total={total:.2f}s"
                            + ("  [no embedding backend]" if no_backend else "")
                            + (f"  [OVER_CEILING {ceiling:.3f}s]" if over_ceiling else ""), root=ROOT)
    if publication_out is not None:
        publication_out.append(publication)
    # the record is banked FIRST, then the honest rc: a capability failure is loud (non-zero)
    # without costing the close the timing evidence of the deposit that DID run.
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
