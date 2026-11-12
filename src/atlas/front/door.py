"""door.py - THE FRONT DOOR: declare -> ingest -> lens -> tree -> faces -> question -> read
-> evidence -> update, as ONE running system.

    scripts/laplace-python -m atlas.front <manifest.json>

Nine stages over retained FrontDoor record/lens/tree state, each emitting one frozen
``StageReceipt`` whose address chains to the one before it. Hash linkage is not
complete source/currentness or scientific verification; question emission records
its exact typed-capability source check separately. There is no measurement script in
this package and no instrument: every number this packet reports is read off one of these
receipts, which is what "the measurement scripts are DELETED into the receipts" means.

  1 declare    the dataset declaration, content-addressed          -> DatasetDeclaration
  2 ingest     into the PERSISTED record (segments.store_ingestion) -> IngestReceipt + manifest
               or, when the segment store already holds the items, ``segments.open_record``,
               which is the stage that re-ingests NOTHING: its OpenReceipt reports extractions
               0, parses 0, source_reads 0.
  3 lens       the declared lens over that record                   -> LensDeclaration
  4 tree       the whole graded tree, kept, batched, PERSISTED      -> GradedTree + manifest
               (on a second run: ``load_tree``, and components re-graded 0)
  5 faces      every face as a RANGE REDUCTION over the persisted
               bytes, and the coarse relation counts as a SPARSE
               triple                                              -> LoadedLens
  6 question   the declared question compiled to typed conditions   -> CompiledQuestion
  7 read       the frontier descent: certificate or refusal, with
               the handles of the content the answer was drawn from -> ReadResult
  8 evidence   the answer's rows within the declared byte budget,
               partial supply against whole supply                 -> the evidence block
  9 update     one item changed: what is re-ingested and re-ranked  -> the O(diff) block

THE DECLARED DRAW is in ``draw.py`` and is stated by the plan, not chosen here: the engine's
ledgers whole, the toy whole, LongMemEval haystacks 0-9 and QASPER dev papers 0-19 as the SMOKE
of the two benchmarks. Every number of this packet comes from that one draw, which is the J1
residual "no two lanes share a draw" closed for this wave.

Complexity: the stages' own, dominated by ingestion O(bytes) on a cold run and by the tree's UP
recursion; a warm run is O(persisted bytes) to open plus the read's own O(supplied positions).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch

from ..grading import tree as T

from ..record import segments as S
from ..record.extract import extractor_roster_hash
from ..store import CompressedHive
from . import faces as FA
from . import joint as JN
from . import joint_section as JS
from . import planner as PL
from . import read as RD
from .draw import DatasetRun, declared_draw, runs_of_the_draw, dataset_names
from .lift import lift_receipt
from ..lifted import require_current, stable_basis
from .question import as_obligation_plan, as_query_plan, compile_question
from .receipts import (Clock, FrontDoorReceipt, StageReceipt, serialize_dataset_run,
                       FRONT_DOOR_RUN_RECORD)

__all__ = ["run_dataset", "run_front_door", "FrontDoor", "FrontInputUnavailable"]


class FrontInputUnavailable(FileNotFoundError):
    """The declared source-only toy input is absent; no alternative input is chosen."""

    def __init__(self, path: Path):
        self.result = {
            "reason": "FRONT-TOY-INPUT-UNAVAILABLE", "dataset": "toy",
            "path": str(path), "publication": "NOT_STARTED",
            "resolution": "Use the source checkout with the exact tracked "
                          "evidence/ATLAS_PROGRAMME/lane_c/toy_corpus.py fixture. "
                          "The Atlas wheel does not carry this input; manifest.root "
                          "selects state, not a replacement dataset.",
        }
        super().__init__(self.result["reason"] + ": " + str(path))


def _require_dataset_inputs(names: Sequence[str]) -> None:
    """Preflight the existing toy owner before supported entries create state."""
    if "toy" in names:
        from ..record.ingest import toy
        if not toy.FIXTURE_PATH.is_file():
            raise FrontInputUnavailable(toy.FIXTURE_PATH)


class FrontDoor:
    """One dataset's whole path, with the receipt chain it emits.

    It holds no policy: the dataset's declaration, ingester, lenses and questions are the
    ``DatasetRun`` the declared draw names, and every decision it makes is either that
    declaration or a receipt.
    """

    __slots__ = ("run", "root", "store", "hive", "stages", "opened", "tree", "manifest",
                 "manifests", "lens", "lens_other", "loaded", "loaded_other", "columns",
                 "joint", "planner", "readings", "results", "clock", "frames", "section_read")

    def __init__(self, run: DatasetRun, root: Path) -> None:
        self.run = run
        self.root = root
        self.store = S.SegmentStore(root / "record")
        self.hive = CompressedHive(root / "tree-hive")
        self.stages: list[StageReceipt] = []
        self.opened: Any = None
        self.tree: T.GradedTree | None = None
        self.manifest: dict[str, Any] | None = None
        self.manifests: dict[str, dict[str, Any]] = {}
        self.lens: Any = None
        self.lens_other: Any = None
        self.loaded: FA.LoadedLens | None = None
        self.loaded_other: FA.LoadedLens | None = None
        self.columns: FA.RankedColumns | None = None
        self.joint: Any = None
        self.planner: Any = None
        self.readings: dict[str, Any] = {}
        self.results: list[dict[str, Any]] = []
        self.clock = Clock()
        # THE NODE FRAME TABLE of the primary lens, and the joint-section read built over it.
        # The frames are persisted with the tree (``grading/frames.py persist_frames``, an organ
        # that existed and had no caller), so the WARM door reads them back instead of rebuilding
        # - which is what makes the joint-section read runnable on a reopened door at all.
        self.frames: Any = None
        self.section_read: JS.JointSectionRead | None = None

    # ---------------------------------------------------------------- the chain
    def _emit(self, stage: str, emits: str, executed: Mapping[str, Any], seconds: float,
              gate_seconds: float, payload: Mapping[str, Any], *,
              diagnostics: Mapping[str, Any] | None = None) -> StageReceipt:
        previous = self.stages[-1] if self.stages else None
        receipt = StageReceipt(
            stage=stage, consumes=(previous.stage if previous else ""),
            consumes_address=(previous.address if previous else ""), emits=emits,
            executed=dict(executed), seconds=seconds, gate_seconds=gate_seconds,
            payload=dict(payload), diagnostics=dict(diagnostics or {}))
        self.stages.append(receipt)
        return receipt

    # ---------------------------------------------------------------- 1 declare
    def declare(self) -> StageReceipt:
        clock = Clock()
        declaration = self.run.declaration()
        gate = time.perf_counter()
        kinds = tuple(spec.kind for spec in declaration.row_kinds)  # loop-ok: the declaration's own row kinds
        relations = tuple(spec.kind for spec in declaration.relation_kinds)  # loop-ok: the declaration's own relation kinds
        gate_seconds = time.perf_counter() - gate
        return self._emit(
            "declare", "DatasetDeclaration",
            {"row_kinds": len(kinds), "relation_kinds": len(relations),
             "columns": sum(len(spec.columns) for spec in declaration.row_kinds)},  # loop-ok: the declaration's own row kinds
            clock.seconds, gate_seconds,
            {"dataset_id": declaration.dataset_id,
             "declaration_hash": declaration.declaration_hash,
             "row_kinds": list(kinds), "relation_kinds": list(relations)})

    # ---------------------------------------------------------------- 2 ingest
    def ingest(self) -> StageReceipt:
        clock = Clock()
        declaration = self.run.declaration()
        warm = bool(self.store.rows()) and self.run.can_open
        if warm:
            self.opened = S.open_record(self.store, declaration, rung=self.run.rung)
            receipt = self.opened.receipt.as_dict()
            executed = {"path": "open_record", "extractions": receipt["extractions"],
                        "parses": receipt["parses"], "source_reads": receipt["source_reads"],
                        "hive_gets": receipt.get("hive_gets", 0),
                        "hive_bytes": receipt.get("hive_bytes", 0),
                        "rows": receipt.get("rows", 0),
                        "relations": receipt.get("relations", 0),
                        "spans": receipt.get("spans", 0)}
            payload = {"open_receipt": receipt}
        else:
            ingestion = self.run.ingest(self.store)
            # The content pass runs INSIDE ``store_ingestion`` (its docstring says why), so the
            # leaves are in the segment the cut writes and this stage only reports them.
            ingest_receipt = S.store_ingestion(
                self.store, ingestion, extractor_roster_hash=extractor_roster_hash())
            self.opened = _Opened(ingestion, ingest_receipt)
            as_dict = ingest_receipt.as_dict()
            executed = {"path": "store_ingestion", "items": as_dict.get("items", 0),
                        "rows": as_dict.get("rows", 0),
                        "relations": as_dict.get("relations", 0),
                        "spans": as_dict.get("spans", 0),
                        "source_bytes": as_dict.get("source_bytes", 0),
                        "persisted_bytes": as_dict.get("persisted_bytes", 0)}
            payload = {"ingest_receipt": as_dict,
                       "content_build": as_dict.get("content", {}),
                       "content_digests": S.content_digests(ingestion)}
            if self.run.can_open and not self.store.rows():
                # MEASURED, and stated rather than hidden: this run cut no manifest row, so a
                # second run cannot open anything.
                #
                # CORRECTED 2026-09-22. The text here used to give the cause as "toy.py and
                # engine_rows.py do not call ingestion.item()", and that was FALSE: both call
                # it (``record/ingest/toy.py:201``, ``record/ingest/engine_rows.py:254``, and
                # the same calls are in HEAD). Measured by
                # ``evidence/ATLAS_PROGRAMME/waves/P1-the-leaf/toy_engine_persistence.py``:
                # each marks ONE item, ``store_ingestion`` cuts one segment carrying its rows,
                # relations, spans and content leaves, and ``open_record`` rebuilds all of it
                # with extractions 0, parses 0 and source_reads 0. A receipt that names a cause
                # it has not measured is worse than one that names none, so this block now
                # reports only what it can see - the counters - and points at the instrument.
                payload["warm_path_not_taken"] = {
                    "why": "the segment store holds no manifest row for this dataset",
                    "measured_by": ("evidence/ATLAS_PROGRAMME/waves/P1-the-leaf/"
                                    "toy_engine_persistence.py, which reports per dataset the "
                                    "items marked, the segment cut and what open_record "
                                    "rebuilds"),
                    "items_marked": int(as_dict.get("items", 0) or 0),
                    "manifest_rows_appended": int(as_dict.get("manifest_rows_appended", 0) or 0)}
        gate = time.perf_counter()
        duplicates = self.opened.ingestion.duplicate_rows()
        gate_seconds = time.perf_counter() - gate
        payload["duplicate_rows_under_B2_identity"] = duplicates
        payload["persisted_bytes_per_source_byte"] = _bytes_per_source_byte(self.opened)
        # THE LEAF'S OWN RECEIPT, on both paths. On the warm path it is what ``open_record``
        # rebuilt from the segments and nothing was encoded; on the cold path it is what the
        # content pass just built. Empty when no axis is declared.
        leaves = getattr(self.opened.ingestion, "content", None)
        payload["content_leaves"] = (
            {} if leaves is None or not len(leaves)
            else leaves.receipt(declaration))
        return self._emit("ingest", "OpenedRecord", executed, clock.seconds, gate_seconds,
                          payload)

    # ---------------------------------------------------------------- 3 lens
    def lens_stage(self) -> StageReceipt:
        clock = Clock()
        self.lens = self.run.lens(self.opened.ingestion)
        # EVERY lens the dataset declares is declared HERE, so that the tree stage persists one
        # tree per lens and the fourth typed residual is a function of two PERSISTED objects.
        self.lens_other = (self.run.second_lens(self.opened.ingestion)
                           if self.run.second_lens is not None else None)
        gate = time.perf_counter()
        self.lens.check_against(self.opened.ingestion.declaration)
        if self.lens_other is not None:
            self.lens_other.check_against(self.opened.ingestion.declaration)
        gate_seconds = time.perf_counter() - gate
        return self._emit(
            "lens", "LensDeclaration",
            {"carrier_row_kinds": len(self.lens.carrier_row_kinds),
             "counted_relation_kinds": len(self.lens.counted_relation_kinds),
             "declared_lenses": 1 if self.lens_other is None else 2,
             "declared_questions": len(self.lens.questions)},
            clock.seconds, gate_seconds,
            {"lens_id": self.lens.lens_id, "lens_hash": self.lens.lens_hash(),
             "second_lens_id": (self.lens_other.lens_id
                                if self.lens_other is not None else None),
             "carrier_row_kinds": list(self.lens.carrier_row_kinds),
             "counted_relation_kinds": list(self.lens.counted_relation_kinds),
             "walk_horizon": self.lens.walk_horizon,
             "horizon_derivation": self.lens.horizon_derivation})

    # ---------------------------------------------------------------- 4 tree
    def _tree_of(self, lens: Any, *, rebuild: bool) -> tuple[dict[str, Any], dict[str, Any],
                                                             dict[str, Any], Any]:
        """ONE lens's tree: loaded from its manifest when it is there, built and PERSISTED once
        when it is not. Every declared lens takes this path, so nothing is rebuilt per run and
        nothing is rebuilt per question. Returns (manifest, executed, payload, built tree)."""
        path = self.root / f"tree-{lens.lens_id}.manifest.json"
        if path.is_file() and not rebuild:
            manifest = json.loads(path.read_text())
            return manifest, {
                "lens_id": lens.lens_id, "path": "load_tree", "components_regraded": 0,
                "svd_batches": 0, "components": len(manifest["components"]),
                "persisted_bytes": int(manifest["persisted_bytes"])}, {
                "lens_id": lens.lens_id,
                "manifest_digest": manifest["manifest_digest"],
                "lens_hash": manifest["lens_hash"],
                "persist_receipt": manifest.get("persist_receipt", {})}, None
        built = T.build_graded_tree(self.opened.ingestion, lens)
        manifest = T.persist_tree(built, self.hive,
                                  self.opened.ingestion.store.identity_by_global())
        if built.frames is not None:
            from ..grading.frames import persist_frames

            manifest["frames"] = persist_frames(built.frames, self.hive)
        receipt = T.receipt_with_persistence(built.receipt, manifest)
        path.write_text(json.dumps(manifest, indent=1))
        as_dict = receipt.as_dict()
        return manifest, {
            "lens_id": lens.lens_id, "path": "build_graded_tree",
            "components": as_dict["components"], "nodes_total": as_dict["nodes_total"],
            "rows_bound": as_dict["rows_bound"], "rows_declared": as_dict["rows_declared"],
            "svd_batches": as_dict["svd_batches"],
            "padded_demand_entries": as_dict["padded_demand_entries"],
            "components_regraded": as_dict["components"]}, {
            "lens_id": lens.lens_id, "grading_receipt": as_dict,
            "manifest_digest": manifest["manifest_digest"],
            "persist_receipt": manifest["persist_receipt"],
            "bytes_per_source_byte": as_dict["bytes_per_source_byte"],
            "persisted_bytes": as_dict["persisted_bytes"]}, built

    def tree_stage(self, *, rebuild: bool = False) -> StageReceipt:
        clock = Clock()
        lenses = [self.lens] if self.lens_other is None else [self.lens, self.lens_other]
        per_lens: list[dict[str, Any]] = []
        payloads: list[dict[str, Any]] = []
        for lens in lenses:  # loop-ok: the lenses this dataset DECLARES, one or two
            manifest, executed_one, payload_one, built = self._tree_of(lens, rebuild=rebuild)
            self.manifests[lens.lens_id] = manifest
            per_lens.append(executed_one)
            payloads.append(payload_one)
            if lens is self.lens:
                self.manifest = manifest
                self.tree = built
        executed = dict(per_lens[0])
        executed["lenses_persisted"] = len(per_lens)
        executed["per_lens"] = per_lens
        payload = dict(payloads[0])
        payload["per_lens"] = payloads
        gate = time.perf_counter()
        gate_seconds = time.perf_counter() - gate
        return self._emit("tree", "PersistedGradedTree", executed, clock.seconds, gate_seconds,
                          payload)

    # ---------------------------------------------------------------- 5 faces
    def faces_stage(self) -> StageReceipt:
        clock = Clock()
        device = self.opened.ingestion.device
        identities = self.opened.ingestion.store.identity_by_global()
        # WHAT THE OPEN COSTS, PIECE BY PIECE. This stage now carries work that used to be done
        # per question (the ranked columns) or not at all on a reopened door (the second lens
        # and the residual), so its seconds are broken down here rather than left as one number
        # a reader has to attribute.
        started = time.perf_counter()
        self.loaded = FA.load_persisted_lens(self.manifest, self.hive, device, identities)
        lens_a_seconds = time.perf_counter() - started
        started = time.perf_counter()
        self.loaded_other = (
            FA.load_persisted_lens(self.manifests[self.lens_other.lens_id], self.hive, device,
                                   identities)
            if self.lens_other is not None else None)
        lens_b_seconds = time.perf_counter() - started
        # THE (RECORD, LENS) WORK, DONE WHERE THE LENS IS OPENED. Every ranked column and every
        # row-kind mask is a function of the record and this lens alone, so they are gathered
        # here, once, and every question of the run reads them. Before this they were rebuilt
        # inside read(), admission_axes and direct_answer - up to three O(M) gathers per column
        # per question, and again for the next question.
        started = time.perf_counter()
        self.columns = FA.RankedColumns(self.opened.ingestion.store, self.loaded)
        opened_columns = self.columns.open_every_declared_column()
        opened_columns["seconds_gathering_the_ranked_columns"] = (time.perf_counter() - started)
        opened_columns["seconds_loading_this_lens"] = lens_a_seconds
        opened_columns["seconds_loading_the_second_lens"] = lens_b_seconds
        # THE READ PLANNER'S OWN (RECORD, LENS) CONSTANTS, built where the lens is opened: the
        # postings index (code -> rank positions, so a single-column exact condition is answered
        # in O(matches)), and the cost model, MEASURED on this device so that a route is chosen on
        # a price and never on a literal. The per-node cut counts are built on first use by the
        # class that needs them and are counted separately.
        started = time.perf_counter()
        # THE PLANNER IS OPENED WITH THE LENS'S OWN HIVE AND ITS OWN LEDGER, so the per-node count
        # tables it needs are PERSISTED beside the node table they index (rule (4): anything that
        # depends only on (record, lens, declared axes) is computed once and persisted). A cold
        # open builds the lens's declared axes and writes them; a warm open reads them back and
        # rebuilds one of them to check that warm equals cold.
        self.planner = PL.ReadPlanner(
            self.opened, self.loaded, self.columns, self.lens, hive=self.hive,
            manifest_path=self.root / f"cut-counts-{self.lens.lens_id}.manifest.json")
        opened_columns["seconds_opening_the_read_planner"] = time.perf_counter() - started
        opened_columns.update(self.planner.executed)
        # THE FRAME TABLE, loaded from the hive by its own content address when the tree stage
        # persisted one, or taken from the tree this run built. No frame is recomputed.
        started = time.perf_counter()
        self.frames = getattr(self.tree, "frames", None) if self.tree is not None else None
        frames_row = (self.manifest or {}).get("frames")
        if self.frames is None and frames_row:
            from ..grading.frames import load_frames

            self.frames = load_frames(self.hive, frames_row["key"], device)
        opened_columns["seconds_loading_the_node_frames"] = time.perf_counter() - started
        opened_columns["node_frames"] = dict(frames_row or {}) if frames_row else {}
        if self.frames is not None:
            started = time.perf_counter()
            self.section_read = JS.JointSectionRead(
                self.opened, self.loaded,
                ({self.lens_other.lens_id: self.loaded_other}
                 if self.loaded_other is not None else {}),
                self.frames, self.columns, self.lens,
                self.lens.carrier_row_kinds[0])
            opened_columns["seconds_building_the_joint_section_read"] = (
                time.perf_counter() - started)
            opened_columns["membership_axes"] = self.section_read.membership.executed.get(
                "axes", 0)
        started = time.perf_counter()
        boundaries = _root_frontier(self.loaded)
        coarse: dict[str, Any] = {}
        for kind in self.lens.counted_relation_kinds[:1]:  # loop-ok: ONE counted relation kind is enough to exercise B.36's coarse graph at this grade; the rest are the same call
            table = self.opened.ingestion.relations.kind(kind)
            if table is not None and len(table):
                # B.36's equality is checked at THIS LENS'S OWN REAL FRONTIER SIZE, not at
                # F in [2, 8] (B2's escalated deficiency 1): the dense form is asked for, and
                # ``ranges.coarse_relation_counts`` either builds it inside its own declared
                # device budget or REFUSES BY NAME - which is itself the measurement, recorded
                # here rather than avoided by a caller-side size guess.
                from ..grading.ranges import RangeRefusal

                try:
                    counts = FA.coarse_counts_over_frontier(self.loaded, table, boundaries,
                                                            dense=True)
                    dense_refusal = None
                except RangeRefusal as refusal:
                    counts = FA.coarse_counts_over_frontier(self.loaded, table, boundaries,
                                                            dense=False)
                    dense_refusal = {"refusal": refusal.refusal, "context": refusal.context}
                coarse = {"kind": kind, "sparse": counts["sparse"],
                          "dense": counts.get("dense"), "dense_refusal": dense_refusal,
                          "sparse_equals_dense": (
                              None if "dense_matrix" not in counts else
                              bool(int(counts["dense_matrix"].sum())
                                   == int(counts["triple"][2].sum())
                                   and int((counts["dense_matrix"] > 0).sum())
                                   == int(counts["triple"][0].numel())))}
        opened_columns["seconds_coarse_relation_counts"] = time.perf_counter() - started
        started = time.perf_counter()
        lateral = self._lateral_residual()
        opened_columns["seconds_lateral_residual"] = time.perf_counter() - started
        gate = time.perf_counter()
        gate_seconds = time.perf_counter() - gate
        executed = dict(self.loaded.executed)
        executed["root_ranges"] = int(boundaries.numel()) - 1
        executed.update(opened_columns)
        return self._emit("faces", "LoadedLens", executed, clock.seconds, gate_seconds,
                          {"lens_hash": self.loaded.lens_hash,
                           "components": self.loaded.components,
                           "nodes": self.loaded.nodes, "rows": self.loaded.rows,
                           "rows_the_lens_could_not_seat": self.loaded.unbound,
                           "coarse_relation_counts": coarse,
                           "lateral_residual": lateral})

    def _lateral_residual(self) -> dict[str, Any]:
        """THE FOURTH TYPED RESIDUAL, when the dataset declares a second lens.

        Two lenses over ONE record disagree, and that disagreement is the commutator of their
        block projectors on the rows they BOTH seat - a typed quantity of its own, never fused
        with closure, price or reconstruction error. Every sentence here is built from the value
        it quotes, computed once (the J1 residual about a report sentence its own number
        contradicts): ``shared_carrier_rows`` and the reading come from the same call.

        BOTH LENSES ARE LOADED, NEITHER IS REBUILT. A tree is persisted per lens by the tree
        stage, and a loaded lens carries its own blocking (the leaves of its persisted node
        table) and its own reference measure (``rank_pi``, written with the tree). So this
        number comes through the declared entry on the REOPENED door, which is what ruling 2
        requires of every headline number - where before it called ``build_graded_tree`` on the
        second lens on every cold run and was simply not produced on a warm one.
        """
        if self.loaded_other is None:
            return {"measured": False,
                    "why": "this dataset declares one lens: the residual is a function of two"}
        if self.loaded.rank_pi is None or self.loaded_other.rank_pi is None:
            return {"measured": False, "lens_a": self.lens.lens_id,
                    "lens_b": self.lens_other.lens_id,
                    "why": ("a persisted component of one of these lenses was cut before the "
                            "reference measure was written with it (header key "
                            "reference_measure); rebuild the tree to measure the residual")}
        device = self.opened.ingestion.device
        rows_a, rows_b = self.loaded.rank_global, self.loaded_other.rank_global
        shared = rows_a[torch.isin(rows_a, rows_b)]
        if not shared.numel():
            return {"measured": False, "lens_a": self.lens.lens_id,
                    "lens_b": self.lens_other.lens_id,
                    "why": "the two lenses seat no row in common on this record"}
        index_a = _position_of(rows_a, shared, device)
        index_b = _position_of(rows_b, shared, device)
        # the block LABELS are compacted to the blocks the shared carrier actually meets, which
        # changes no value of the commutator (an empty block contributes nothing to either
        # projector) and keeps the overlap matrix the two lenses' own block counts.
        _, mine = torch.unique(FA.leaf_label_of_rank(self.loaded).index_select(0, index_a),
                               return_inverse=True)
        _, theirs = torch.unique(
            FA.leaf_label_of_rank(self.loaded_other).index_select(0, index_b),
            return_inverse=True)
        reading = T.lateral_residual(mine, self.loaded.rank_pi.index_select(0, index_a),
                                     theirs,
                                     self.loaded_other.rank_pi.index_select(0, index_b))
        reading.update({"measured": True, "lens_a": self.lens.lens_id,
                        "lens_b": self.lens_other.lens_id,
                        "why_two_lenses": self.run.second_lens_why,
                        "both_lenses_were_loaded_not_rebuilt": True,
                        "lens_b_receipt": {
                            "components": self.loaded_other.components,
                            "nodes_total": self.loaded_other.nodes,
                            "rows_bound": self.loaded_other.rows,
                            "components_regraded": self.loaded_other.executed[
                                "components_regraded"]}})
        return reading

    def _question_stage(self, compiled, clock: Clock) -> StageReceipt:
        """The actual answer_stage question emission, independently inspectable on CPU.

        This projects already compiled conditions; it does not ingest, build a tree,
        execute a numerical read, or establish warm persisted-tree currentness.
        The exact lifted owner checks its consumed basis before a successful stage
        can enter the chain. Unknown/changed required source is a named refusal.
        """
        plans = [as_query_plan(c) for c in compiled]  # loop-ok: the dataset's own question list
        obligations = [as_obligation_plan(c, p)
                       for c, p in zip(compiled, plans)]  # loop-ok: the dataset's own question list
        # The consumed basis is the owner's retained first-adapter observation,
        # not a freshly hashed file posing as the code that constructed the types.
        basis = lift_receipt(("query_plan", "query_obligations"), observe_current=False)
        gate = Clock()
        current = require_current(basis)
        gate_seconds = gate.seconds
        compiled_rows, compiled_seconds = [], []
        for question in compiled:
            row = question.as_dict()
            compiled_seconds.append(row.pop("seconds"))
            compiled_rows.append(row)
        return self._emit(
            "question", "CompiledQuestion",
            {"questions": len(compiled),
             "typed_plan_objects": sum(len(p.claims) + len(p.lexical_candidates)
                                       + len(p.context_bindings) + len(p.evidence_obligations)
                                       for p in plans),  # loop-ok: the compiled question list
             "conditions": sum(len(c.coded) for c in compiled),  # loop-ok: the compiled question list
             "anchors_resolved": sum(int(c.anchor.get("resolved", 0)) for c in compiled)},  # loop-ok: the compiled question list
            clock.seconds, gate_seconds,
            {"compiled": compiled_rows,
             "lifted_plan_shape": {"module": "atlas.reconstruction.query_plan",
                                   "adapter_version": "atlas.front.question/2",
                                   "plans": [p.to_dict() for p in plans]},  # loop-ok: the compiled question list
             "lifted_obligation_shape": {
                 "module": "atlas.reconstruction.query_obligations",
                 "plans": [{"version": o.version, "status": o.status,
                            "attachments": [a.id for a in o.attachments],  # loop-ok: this plan's own attachment rows
                            "issues": list(o.issues)} for o in obligations]},  # loop-ok: the compiled question list
             "lifts": stable_basis(basis), "source_currentness": stable_basis(current)},
            diagnostics={"lifts": basis.get("diagnostics", {}),
                         "source_currentness": current.get("diagnostics", {}),
                         "compiled_seconds": compiled_seconds})


    # ---------------------------------------------------------------- 6-8 question, read, evidence
    def answer_stage(self, *, tolerance_index: int = 0,
                     supplies: Sequence[str] = ("partial", "whole")) -> tuple[StageReceipt,
                                                                             StageReceipt,
                                                                             StageReceipt]:
        clock = Clock()
        compiled = []
        for spec in self.run.questions(self.opened):  # loop-ok: the dataset's own declared question list
            compiled.append(compile_question(spec, self.opened, self.lens, self.loaded.rows,
                                             loaded=self.loaded, columns=self.columns))
        question_receipt = self._question_stage(compiled, clock)

        clock = Clock()
        results: list[dict[str, Any]] = []
        # ONE BUILD OF THE CONDITIONAL-LAW QUOTIENT FOR THE WHOLE QUESTION LIST. The quotient is
        # a property of the record and the declared axis set; the lifted spine's own result is
        # an amortisation over a BATCH of queries after one charged build. Building it inside
        # the loop below charged it per question and threw that away.
        self.joint = JN.build_joint_bank(self.opened, self.loaded, compiled,
                                         columns=self.columns)
        # THE READ PLANS BY QUESTION CLASS (wave J4's ruling R1). Every question is CLASSED from
        # its typed plan, priced on the measured cost model and read by the route its class
        # admits - the record's postings, the lens tree frontier, the cut reductions, the exact
        # integer contraction, or the packed scan when the cost model says the scan is cheapest.
        # The tree-route questions descend on ONE SHARED frontier, one launch sequence per round
        # for all of them (must_achieve 3).
        planned, plan_executed = PL.read_questions(
            self.planner, compiled, tolerance_index=tolerance_index, supplies=supplies)
        for compiled_question in compiled:  # loop-ok: the dataset's own declared question list
            qid = compiled_question.spec.qid
            per_question: dict[str, Any] = {"qid": qid,
                                            "text": compiled_question.spec.text,
                                            "plan": planned[qid]["plan"],
                                            "known_answer": compiled_question.spec.known_answer,
                                            "known_answer_source":
                                                compiled_question.spec.known_answer_source}
            for supply in supplies:  # loop-ok: the two declared supply disciplines, partial and whole
                result = planned[qid][supply]
                per_question[supply] = result.as_dict()
                if supply == "partial":
                    per_question["handles"] = result.row_handles.as_dicts()
                    per_question["range_handles_of_the_route"] = (
                        result.range_handles.as_dicts(8))
            control = RD.direct_answer(self.opened, self.loaded, compiled_question,
                                       self.columns)
            per_question["flat_control"] = control
            per_question["answer_equals_the_flat_control"] = (
                _same(per_question["partial"]["answer"], control["answer"]))
            per_question["packed_direct_control"] = RD.packed_direct_control(
                self.opened, self.loaded, compiled_question, self.columns)
            # must_achieve (13): the EXACT joint count comes from the lifted integer contraction
            # (over gpu_state's conditional-law quotient) and from section_coupling's
            # route-weighted quotient - never inferred from the descent. Both are asked for the
            # same admission axes the read and the packed control use, so the four numbers are
            # one number or the packet is wrong.
            per_question["exact_joint_counts"] = self.joint.for_question(
                compiled_question,
                rows_admitted=per_question["partial"]["executed"]["rows_admitted"])
            if per_question["known_answer"] is not None:
                per_question["answer_equals_the_known_answer"] = _same(
                    per_question["partial"]["answer"], compiled_question.spec.known_answer)
            results.append(per_question)
        self.results = results
        # THE SIX AGGREGATE READINGS OF AN ANSWER, at a cut of this lens, on this dataset's own
        # declared questions (S4B's six observables). They touch |K| nodes and no leaf.
        # THE JOINT-SECTION READ (steps B and C), for the WHOLE question list at once, inside
        # the door's own read stage. It runs where the lens declares a field - the content axis -
        # and is the route the content_question class takes.
        section: dict[str, Any] = {"ran": False,
                                   "why": "this dataset's primary lens declares no field family"}
        if self.section_read is not None:
            section = JS.joint_section_questions(self.section_read, compiled)
            for entry in results:  # loop-ok: this dataset's results
                block = section["questions"].get(entry["qid"])
                if block is not None:
                    entry["joint_section_read"] = block
        self.readings = PL.six_readings(self.planner, compiled)
        gate = time.perf_counter()
        correct = sum(1 for r in results if r.get("answer_equals_the_known_answer"))  # loop-ok: this dataset's results
        agree = sum(1 for r in results if r.get("answer_equals_the_flat_control"))  # loop-ok: this dataset's results
        gate_seconds = time.perf_counter() - gate
        read_receipt = self._emit(
            "read", "ReadResult",
            {"questions_read": len(results),
             "certificates": sum(1 for r in results
                                 if r["partial"]["certificate"] is not None),  # loop-ok: this dataset's results
             "refusals": sum(1 for r in results if r["partial"]["refusal"] is not None),  # loop-ok: this dataset's results
             "answers_equal_to_the_flat_control": agree,
             "answers_equal_to_a_known_answer": correct,
             "reduction_calls": sum(r["partial"]["executed"]["reduction_calls"]
                                    for r in results),  # loop-ok: this dataset's results
             "packed_direct_scan_counts_equal_to_rows_admitted": sum(
                 1 for r in results
                 if r["packed_direct_control"].get("count")
                 == r["partial"]["executed"]["rows_admitted"]),  # loop-ok: this dataset's results
             "exact_joint_counts_agreeing_with_the_read": sum(
                 1 for r in results
                 if r["exact_joint_counts"].get("agreement", {}).get("all_three_agree")),  # loop-ok: this dataset's results
             # WHAT THE WHOLE QUESTION LIST CHARGED, once: the quotient and the coupling builds
             # of the exact spine, and the ranked columns the read reads.
             "joint_quotients_built_for_the_whole_question_list":
                 self.joint.executed["quotients_built"],
             "joint_couplings_built_for_the_whole_question_list":
                 self.joint.executed["couplings_built"],
             "joint_build_seconds": self.joint.executed["build_seconds"],
             "joint_contraction_seconds": self.joint.executed["contraction_seconds"],
             "ranked_columns_built_inside_the_question_loop": sum(
                 r[supply]["executed"]["ranked_columns_built"]
                 for r in results for supply in supplies),  # loop-ok: this dataset's results
             # WHAT THE PLANNER DECIDED AND WHAT BATCHING SAVED, from the run's own counters.
             "routes_chosen": plan_executed["routes"],
             "question_classes": plan_executed["classes"],
             "reduction_calls_batched": plan_executed.get("reduction_calls_batched", 0),
             "reduction_calls_unbatched": plan_executed.get("reduction_calls_unbatched", 0),
             "batched_rounds": plan_executed.get("rounds", 0),
             "questions_on_the_tree": plan_executed.get("questions_batched", 0),
             "planning_seconds": plan_executed["planning_seconds"],
             "joint_section_read": (section.get("executed", {}) if section.get("ran", True)
                                    else {"ran": False}),
             },
            clock.seconds, gate_seconds,
            {"questions": results, "joint_section": section,
             "joint_bank": dict(self.joint.executed),
             "planner": plan_executed, "six_readings": self.readings,
             "cost_model": self.planner.cost.as_dict(),
             "classes_declared": [dict(row) for row in PL.CLASSES]})  # loop-ok: the five declared classes

        clock = Clock()
        evidence = [{"qid": r["qid"], "partial": r["partial"]["evidence"],
                     "whole": r["whole"]["evidence"]} for r in results]  # loop-ok: this dataset's results
        evidence_receipt = self._emit(
            "evidence", "EvidenceWithinABudget",
            {"questions": len(evidence),
             "partial_bytes": sum(e["partial"]["partial_bytes"] for e in evidence),  # loop-ok: this dataset's results
             "whole_bytes": sum(e["whole"]["whole_bytes"] for e in evidence)},  # loop-ok: this dataset's results
            clock.seconds, 0.0, {"evidence": evidence})
        return question_receipt, read_receipt, evidence_receipt

    # ---------------------------------------------------------------- 9 update
    def update_stage(self) -> StageReceipt:
        """ONE item changed: what the record re-ingests and what the tree re-ranks.

        The change is a REAL one - the first bound row of the lens - and the numbers are
        ``tree.reranked_components``' own, reported as components AND as rows, which is the
        measurement the J1 synthesis' seams[6] says decides whether the component is the right
        unit of change at all.
        """
        clock = Clock()
        if self.tree is None or not self.loaded.rows:
            return self._emit("update", "ODiffBlock",
                              {"rows_changed": 0, "components_reranked": 0},
                              clock.seconds, 0.0,
                              {"why": "this run opened the tree instead of building it, so the "
                                      "in-memory GradedTree the re-rank is computed from is not "
                                      "here; the warm path's own numbers are in the tree stage"})
        changed = self.loaded.rank_global[:1]
        block = T.reranked_components(self.tree, changed)
        gate = time.perf_counter()
        gate_seconds = time.perf_counter() - gate
        return self._emit("update", "ODiffBlock",
                          {"rows_changed": block["changed_rows"],
                           "components_reranked": block["components_reranked"],
                           "rows_reranked": block["rows_reranked"]},
                          clock.seconds, gate_seconds, {"reranked": block})

    # ---------------------------------------------------------------- the whole path
    def run_path(self, *, tolerance_index: int = 0) -> FrontDoorReceipt:
        self.declare()
        self.ingest()
        self.lens_stage()
        self.tree_stage()
        self.faces_stage()
        self.answer_stage(tolerance_index=tolerance_index)
        self.update_stage()
        return FrontDoorReceipt(
            record="atlas.front-door/1", dataset_id=self.run.dataset_id,
            draw=self.run.draw, stages=tuple(self.stages), seconds=self.clock.seconds)


class _Opened:
    """The cold path's stand-in for ``segments.OpenedRecord``: the same two attributes the whole
    read path uses, so a cold run and a warm run are ONE code path downstream. O(1)."""

    __slots__ = ("ingestion", "receipt")

    def __init__(self, ingestion: Any, receipt: Any) -> None:
        self.ingestion = ingestion
        self.receipt = receipt


def _bytes_per_source_byte(opened: Any) -> dict[str, Any]:
    receipt = opened.receipt
    as_dict = receipt.as_dict()
    source = int(as_dict.get("source_bytes", 0) or 0)
    persisted = int(as_dict.get("persisted_bytes", 0) or 0)
    device = int(as_dict.get("device_bytes", 0) or 0)
    return {"source_bytes": source, "persisted_bytes": persisted, "device_bytes": device,
            "persisted_per_source": (persisted / source if source else None),
            "device_per_source": (device / source if source else None)}


def _position_of(haystack: torch.Tensor, needles: torch.Tensor,
                 device: torch.device) -> torch.Tensor:
    """Where each needle sits in ``haystack``: one argsort and one searchsorted. O(n log n)."""
    order = torch.argsort(haystack)
    found = torch.searchsorted(haystack[order], needles)
    return order.index_select(0, found.clamp(max=haystack.numel() - 1))


def _root_frontier(lens: FA.LoadedLens) -> torch.Tensor:
    lo = lens.lo.index_select(0, lens.roots)
    hi = lens.hi.index_select(0, lens.roots)
    order = torch.argsort(lo)
    from ..grading.ranges import frontier_boundaries

    return frontier_boundaries(lo[order], hi[order])


def _same(answer: Any, expected: Any) -> bool:
    """Do two answers agree? Lists are compared as sets of strings, so an order that no operator
    declares cannot make two equal answers look different. O(k log k)."""
    if isinstance(expected, (list, tuple, set, frozenset)):
        return sorted(str(v) for v in (answer or [])) == sorted(str(v) for v in expected)
    if isinstance(expected, bool) or isinstance(answer, bool):
        return bool(answer) == bool(expected)
    if isinstance(expected, (int, float)) and isinstance(answer, (int, float)):
        return float(answer) == float(expected)
    return str(answer) == str(expected)


def run_dataset(name: str, root: Path, *, tolerance_index: int = 0,
                draw_id: str | None = None) -> dict[str, Any]:
    """One dataset of the declared draw, through every stage. Returns the whole receipt."""
    wanted = dataset_names((name,))
    _require_dataset_inputs(wanted)
    run = runs_of_the_draw(draw_id, names=wanted)[name]
    door = FrontDoor(run, root / name)
    receipt = door.run_path(tolerance_index=tolerance_index)
    return serialize_dataset_run(name, receipt)


def run_front_door(manifest_path: str | Path, *, datasets: Sequence[str] | None = None,
                   tolerance_index: int = 0) -> dict[str, Any]:
    """THE ONE COMMAND: every stage on every dataset the manifest names, at the declared draw.

    The manifest is the run's own declaration: where the record and the tree hive live, and
    which of the declared draw's datasets to run. It carries no parameter and no threshold -
    a dial in a manifest would be a hand-set literal by another name.
    """
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    root = Path(manifest["root"]).expanduser()
    # THE DRAW IS A DECLARED ROW THE MANIFEST NAMES BY ID (the J2 synthesis' seams[13]: the
    # manifest used to name a plan file that contained no draw key, which is a reference that
    # cannot be resolved). An id no row declares is refused here, not defaulted.
    draw_id = manifest.get("declared_draw")
    draw = declared_draw(draw_id)
    wanted = dataset_names(datasets, fallback=manifest.get("datasets"))
    _require_dataset_inputs(wanted)
    root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    out: dict[str, Any] = {"record": FRONT_DOOR_RUN_RECORD,
                           "manifest": str(manifest_path), "root": str(root),
                           "declared_draw": draw, "datasets": {}}
    for name in wanted:  # loop-ok: the datasets the declared draw names (four)
        out["datasets"][name] = run_dataset(name, root, tolerance_index=tolerance_index,
                                            draw_id=draw_id)
    out["seconds"] = time.perf_counter() - started
    return out
