"""Store-backed DOWN retrieval, not a measurement of the whole container.

Read protocol: score stored centroid/retained-basis and semantic faces, descend
the declared beam through all stored grades, rank its stored member vectors. Serve text ONLY by
mapping generation.clauses source_path/start/end to SnapshotView leaf spans and
reading through SpanReader. Never call reconstruct_blueprint, _fresh, transport,
or read source files. No query-time store mutation, including first-role transport.
Semantic faces are embedded once in fold, in one counted batch; every query
embedding is counted. Original pour costs remain explicitly unknown if unreceipted.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

import numpy as np

from ...blueprint import current_blueprint_generation
from ...dataset import extra_authority_files
from ...encoders.bge_onnx import BgeOnnxEncoder
from ...errors import ProtocolViolation
from ...ids import hash_bytes
from ...store import ConceptricStore
from ..cost import FoldCost, ModelCounter, tokens_of
from ..protocol import ArmProtocol
from .base import ArmAnswer, BaseArm


@dataclass
class AtlasFoldCost(FoldCost):
    """A missing historical bill is null, never a zero-cost cached pour."""
    historical_costs: dict | None = None

    def to_dict(self):
        result = super().to_dict()
        result['retrieval_setup'] = dict(result)
        result['pour_cost_status'] = 'KNOWN' if self.historical_costs is not None else 'MISSING_POUR_COST_RECEIPT'
        result['historical_pour'] = self.historical_costs
        if self.historical_costs is None:
            for name in ('wall_seconds', 'model_calls', 'model_tokens', 'vectors_built', 'bytes_stored'):
                result[name] = None
        else:
            result['wall_seconds'] += self.historical_costs['wall_seconds']
            result['model_calls'] += self.historical_costs['encoder_calls']
            result['vectors_built'] += self.historical_costs['vectors_built']
            # Pour receipts do not meter model tokens or persisted store bytes.
            result['model_tokens'] = result['bytes_stored'] = None
        return result

    def amortized(self, reference_query_count):
        result = super().amortized(reference_query_count)
        result['retrieval_setup'] = dict(result)
        totals = self.to_dict()
        for field, total in [('wall_seconds_per_query', 'wall_seconds'),
                             ('model_calls_per_query', 'model_calls'),
                             ('model_tokens_per_query', 'model_tokens'),
                             ('bytes_stored_per_query', 'bytes_stored')]:
            result[field] = (totals[total] / reference_query_count if totals[total] is not None else None)
        return result


def cosine(left, right):
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denom) if denom else 0.0


FACE_SCORE_LAWS = ('equal-mean', 'frame-residual', 'semantic-only', 'centroid-only',
                   'sum-of-heat-through-the-nest')


def face_score(query, spectral, semantic_vector, law='equal-mean'):
    """Equal-weight cosine to query projected onto affine frame and semantic face."""
    if law not in FACE_SCORE_LAWS:
        raise ProtocolViolation('ATLAS_UNKNOWN_FACE_SCORE', law=law)
    query = np.asarray(query, dtype=float)
    if law == 'semantic-only':
        return cosine(query, semantic_vector)
    centre = np.asarray(spectral['centroid'], dtype=float)
    if law == 'centroid-only':
        return cosine(query, centre)
    basis = np.asarray(spectral['frame']['basis'], dtype=float).reshape((-1, len(centre)))
    projected = centre + basis.T @ (basis @ (query - centre))
    if law == 'frame-residual':
        delta = query - centre
        energy = float(np.dot(delta, delta))
        residual = query - projected
        return float(np.clip(1 - np.dot(residual, residual) / energy, 0, 1)) if energy else 1.0
    return (cosine(query, projected) + cosine(query, semantic_vector)) / 2


class AtlasArm(BaseArm):
    def __init__(self, store_root: Path, k=10, seed=20260801, model_dir=None,
                 reference_queries=80, encoder=None, authority_root=None, beam=1, face_score_law='equal-mean'):
        if reference_queries <= 0 or k <= 0 or type(beam) is not int or beam < 1:
            raise ProtocolViolation('ATLAS_INVALID_READ_PROTOCOL')
        if face_score_law not in FACE_SCORE_LAWS:
            raise ProtocolViolation('ATLAS_UNKNOWN_FACE_SCORE', law=face_score_law)
        self.face_score_law = face_score_law
        self.store_root = Path(store_root)
        self.authority_root = Path(authority_root) if authority_root else Path(__file__).resolve().parents[4]
        self.reference_queries = reference_queries
        if encoder is None:
            from ...runtime import preload_cuda_libraries
            preload_cuda_libraries()
        self.encoder = encoder or BgeOnnxEncoder(model_dir=model_dir, threads=2,
                                               providers=('CUDAExecutionProvider',))
        self.require_cuda = encoder is None  # Synthetic injection is only a fixture seam.
        self.protocol = ArmProtocol(
            arm_id='atlas', variant='', segmentation_recipe_version='stored-generation/1',
            input_recipe_version=('atlas-affine-frame-semantic-equal/1' if face_score_law == 'equal-mean'
                                  else f'atlas-face-{face_score_law}/1'),
            encoder_id=self.encoder.encoder_id, schema_version='atlas.blueprint-generation',
            k=k, max_spans_read=k, max_whole_file_reads=0, read_budget_bytes=2_000_000,
            rounds=1, beam=beam, max_materialized=k, granularity='span',
            fold_model_calls=1, query_model_calls=1,
            model_stamp=self.encoder.encoder_id, seed=seed,
            note=('Store faces only for scoring; declared beam per frontier, cosine member rank; '
                  'exact clause-to-SnapshotView spans, counted reads; no transport or source reads. '
                  f'Fold reference queries={reference_queries}; embeddings count as model calls.'))

    def prepare_encoder(self):
        if self.require_cuda:
            import onnxruntime as ort
            if 'CUDAExecutionProvider' not in ort.get_available_providers():
                raise ProtocolViolation('GPU_REQUIRED: atlas CUDA provider unavailable')
            session = self.encoder._load().model.model
            if session.get_providers()[0] != 'CUDAExecutionProvider':
                raise ProtocolViolation('GPU_REQUIRED: atlas encoder fell back')
            session.disable_fallback()
        return self.encoder

    def fold(self, view, segmentation_id=''):
        started = time.perf_counter()
        self.prepare_encoder()
        wal = self.store_root / 'conceptric.sqlite3-wal'
        if wal.is_file() and wal.stat().st_size:
            raise ProtocolViolation('ATLAS_UNCHECKPOINTED_AUTHORITY: immutable read refused')
        store = ConceptricStore(self.store_root, read_only=True, immutable=True,
                                extra_authority_files=extra_authority_files(self.authority_root))
        self.generation = current_blueprint_generation(store)
        if self.encoder.spec.to_dict() != dict(self.generation.encoder_spec or {}):
            raise ProtocolViolation('ATLAS_ENCODER_GENERATION_MISMATCH')
        self.state = store.replay_authority_only()
        # Check metadata only: scoring never reads snapshot blobs or repository text.
        spans = {(s.node_id, s.start, s.end): s for s in view.leaf_spans}
        self.clauses = {c['logical_id']: c for c in self.generation.clauses}
        self.spans = {}
        for key, clause in self.clauses.items():
            span = spans.get((clause['source_path'], clause['start'], clause['end']))
            node = view.bundle.nodes.get(clause['source_path'])
            if span is None or node is None or node.content_hash != clause['source_hash']:
                raise ProtocolViolation('ATLAS_SNAPSHOT_CLAUSE_MISMATCH', logical_id=key)
            self.spans[key] = span
        self.clusters = sorted(self.generation.clusters, key=lambda c: c['node_handle'])
        self.cluster_by_id = {c['cluster_id']: c for c in self.clusters}
        if len(self.cluster_by_id) != len(self.clusters):
            raise ProtocolViolation('ATLAS_DUPLICATE_CLUSTER')
        child_ids = [key for c in self.clusters for key in c.get('child_cluster_ids', [])]
        if len(child_ids) != len(set(child_ids)) or set(child_ids) - set(self.cluster_by_id):
            raise ProtocolViolation('ATLAS_INVALID_TREE')
        self.roots = [c for c in self.clusters if c['cluster_id'] not in set(child_ids)]
        reached = set()
        def validate(node, trail):
            key = node['cluster_id']
            if key in trail:
                raise ProtocolViolation('ATLAS_TREE_CYCLE')
            reached.add(key)
            children = [self.cluster_by_id[c] for c in node.get('child_cluster_ids', [])]
            if children:
                members = [k for c in children for k in c['member_logical_ids']]
                if sorted(members) != sorted(node['member_logical_ids']):
                    raise ProtocolViolation('ATLAS_CHILD_MEMBERSHIP_MISMATCH')
                for child in children:
                    if child.get('depth') != node.get('depth', 1) + 1:
                        raise ProtocolViolation('ATLAS_GRADE_CHAIN_MISMATCH')
                    validate(child, trail | {key})
        for root in self.roots:
            validate(root, set())
        if reached != set(self.cluster_by_id):
            raise ProtocolViolation('ATLAS_UNREACHABLE_CLUSTER')
        members = [key for c in self.roots for key in c['member_logical_ids']]
        if set(members) != set(self.clauses) or len(members) != len(set(members)):
            raise ProtocolViolation('ATLAS_CLUSTER_MEMBERSHIP_MISMATCH')
        faces = [self.state.graph_objects[c['semantic_object_id']].attributes['face'] for c in self.clusters]
        models = ModelCounter('atlas:fold')
        self.semantic_vectors = models.call(self.encoder.embed, faces, tokens=sum(map(tokens_of, faces)))
        self.semantic_by_id = {c['cluster_id']: v for c, v in
                               zip(self.clusters, self.semantic_vectors, strict=True)}
        models.assert_declared(self.protocol.fold_model_calls)
        self.fold_cost = AtlasFoldCost(
            wall_seconds=time.perf_counter() - started,
            wall_seconds_this_call=time.perf_counter() - started,
            model_calls=models.calls, model_tokens=models.tokens, vectors_built=len(faces),
            historical_costs=(dict(self.generation.receipt.costs) if self.generation.receipt else None))
        return self.fold_cost

    def answer(self, task, reader, models):
        query = np.asarray(models.call(self.encoder.query, task.question, tokens=tokens_of(task.question)))
        frontier = [(c, 1.0) for c in self.roots]
        candidates = []
        rejected = []
        selected = []
        coarse_scored = 0
        depths = []
        routing_trace = []
        while frontier:
            scored = [(face_score(query,
                self.state.graph_objects[c['spectral_object_id']].attributes,
                self.semantic_by_id[c['cluster_id']], self.face_score_law)
                * (heat if self.face_score_law == 'sum-of-heat-through-the-nest' else 1.0), c)
                for c, heat in frontier]
            scored.sort(key=lambda row: (-row[0], row[1]['node_handle']))
            coarse_scored += len(scored)
            keep = scored[:self.protocol.beam]
            rejected.extend(c['node_handle'] for _, c in scored[self.protocol.beam:])
            routing_trace.append([dict(node_handle=c['node_handle'], grade=c.get('depth', 1),
                                       score=float(score), rank=i + 1, kept=i < self.protocol.beam)
                                  for i, (score, c) in enumerate(scored)])
            frontier = []
            for heat, cluster in keep:
                selected.append(cluster['node_handle'])
                depths.append(cluster.get('depth', 1))
                children = cluster.get('child_cluster_ids', [])
                if children:
                    frontier.extend((self.cluster_by_id[key], heat) for key in children)
                else:
                    candidates.extend(cluster['member_logical_ids'])
        ranked = sorted(candidates, key=lambda key: (
            -cosine(query, self.state.graph_objects[self.clauses[key]['object_id']].attributes['vector']),
            self.clauses[key]['content_handle']))[:self.protocol.k]
        texts = []
        for key in ranked:
            text = reader.read_span(self.spans[key])
            if hash_bytes(text.encode('utf-8')) != self.clauses[key]['exact_byte_hash']:
                raise ProtocolViolation('ATLAS_SNAPSHOT_TEXT_MISMATCH', logical_id=key)
            texts.append(text)
        detail = dict(generation_id=self.generation.generation_id,
                      beam=self.protocol.beam, k=self.protocol.k, face_score=self.face_score_law,
                      routing_trace=routing_trace, visited=len(candidates), total=len(self.clauses),
                      coarse_scored=coarse_scored, coarse_expanded=len(selected),
                      selected_branch=selected[0], selected_branches=selected,
                      grades_descended=depths,
                      rejected_branches=rejected,
                      omission_residual=len(self.clauses) - len(candidates),
                      reads=len(texts), fold_reference_queries=self.reference_queries)
        return ArmAnswer(context='\n\n'.join(texts), rounds=1,
                         retrieved=[self.clauses[key]['content_handle'] for key in ranked],
                         retrieved_texts=texts, detail=detail,
                         note='retrieval-only; unvisited members remain omitted')
