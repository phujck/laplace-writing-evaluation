"""Cross-seal law agreement; each package keeps its measured spectral operator."""
import inspect
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from laplace.engine import meaning_upfold as engine


def test_same_recursive_law_and_grade_one_partition(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'src'))
    from atlas import spectral_pour as container
    from atlas.ids import chash
    # This is a parity harness only: production atlas never imports the engine.
    assert inspect.getsource(engine.recursive_split_stop) == inspect.getsource(container.recursive_split_stop)
    for n, depth, same, k, labels, expected in [
        (2, 1, False, None, None, 'leaf_max'),
        (12, 1, True, None, None, 'indistinguishable_members'),
        (12, 3, False, None, None, 'depth_cap'),
        (12, 1, False, 1, 1, 'silhouette_refused'),
        (12, 1, False, 2, 1, 'chosen_k_collapsed'),
        (12, 1, False, 2, 2, None),
    ]:
        args = dict(leaf_max=2, max_depth=3, indistinguishable=same, chosen_k=k, distinct_labels=labels)
        assert engine.recursive_split_stop(n, depth, **args) == expected
        assert container.recursive_split_stop(n, depth, **args) == expected
    monkeypatch.setenv('LAPLACE_DIALS_ROOT', str(tmp_path))
    engine.dials.pour_genesis(tmp_path)
    engine.dials.set_value('engine-fold', 'branch_max', '2', by='test', why='same planted grade-one cut')
    angles = np.concatenate([np.linspace(0, .1, 6), np.linspace(1.4, 1.5, 6)])
    vectors = np.stack([np.cos(angles), np.sin(angles)], axis=1)
    leaves = [container.PourLeaf(str(i), f'leaf:{i}', chash({'i': i}), str(i), tuple(v), (chash({'i':i}),))
              for i, v in enumerate(vectors)]
    k, labels = engine._best_split_gpu(vectors, level=1)
    engine_partition = {tuple(str(i) for i in range(len(vectors)) if labels[i] == label)
                        for label in set(labels)}
    atlas_partition = {tuple(sorted(c.member_logical_ids, key=int))
                       for c in container.derive_spectral_placement(leaves, 2)}
    assert engine_partition == atlas_partition
    print(json.dumps(dict(grade=1, engine_k=k, atlas_k=2, same_partition=True,
        partition=sorted(engine_partition),
        difference='engine normalized-Laplacian D^-1/2 rescale and seeded Lloyd; atlas row-normalized affinity eigenvectors and content-tie deterministic Lloyd')))
