"""The closure meter is NO LONGER WIRED TO THE DESCENT - and this file proves the absence.

Internals lane seq 1, cause ``walk-banked-not-verdict``. ``recursive_read.descend`` used to append
one ~24 KB row per descent to ``.closure_meter.jsonl``. The store reached 60,101,446 B / 2,459 rows
(2,301 dutiful + 158 unattributed + 0 need) with ZERO readers: ``closure_meter.read_rows`` has no
caller anywhere in ``src/``, ``scripts/`` or ``.claude/``. The whole walk was banked, never a
verdict, and the only class the module's own guard admits as signal never appeared once.

So the old positive half of this file - one row per descend, entered_order, wasted, nu, the fire
class, the degrade paths - tested a seam that is gone. A test of a walk-banking seam is not a gate.
What remains is the NEGATIVE claim, which is the one that must never silently regress: a descent
writes nothing, the packet is unchanged, and the module is inert on the read path.

``closure_meter.py`` itself is left standing: the file stays tracked (untracking is HIS call, and
``sources.py`` / ``recovery_coordinate.py`` still roster the store), and the module goes when it is
retired whole rather than by a test deletion.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from laplace.engine import closure_meter, meaning_upfold, recursive_read

pytest.importorskip("numpy", reason="recursive_read scores with numpy (a declared base dep)")

VERSION = "stub:closure-meter-v1"


class StubBackend:
    """Deterministic four-family geometry. Not the hash router (which open_descender refuses)."""

    name = VERSION
    FAMILIES = ("alpha", "beta", "gamma", "delta")
    dim = 8

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        fam = 0
        for i, key in enumerate(self.FAMILIES):
            if key in text:
                fam, v[i] = i, 1.0
                break
        h = int(hashlib.sha1(text.encode("utf-8")).hexdigest(), 16)
        v[4 + (fam % 4)] += (h % 100) / 500.0
        n = math.sqrt(sum(x * x for x in v))
        return [x / n for x in v] if n else v

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def query(self, text: str) -> list[float]:
        return self._vec(text)


def _unit(vecs: list[list[float]]) -> list[float]:
    acc = [sum(col) / len(vecs) for col in zip(*vecs, strict=True)]
    n = math.sqrt(sum(x * x for x in acc))
    return [x / n for x in acc] if n else acc


@pytest.fixture()
def corpus() -> dict[str, str]:
    return {f"{fam}/doc_{i:02d}.md": f"{fam} document {i} topic{i % 3}"
            for fam in StubBackend.FAMILIES for i in range(10)}


@pytest.fixture()
def tree(corpus) -> dict:
    """root -> a pure-branch cluster per family pair -> two leaf clusters per family."""
    backend = StubBackend()
    clusters: dict[str, dict] = {}
    parent_map: dict[str, str] = {}
    for pair_i, pair in enumerate((("alpha", "beta"), ("gamma", "delta"))):
        branch = f"concept::branch{pair_i}"
        clusters[branch] = {"members": [], "label": f"branch {pair_i}",
                            "centroid": None, "sealed": False}
        parent_map[branch] = ""
        for fam in pair:
            names = sorted(n for n in corpus if n.startswith(fam + "/"))
            for half, chunk in enumerate((names[:5], names[5:])):
                cid = f"concept::{fam}{half}"
                vecs = backend.embed([corpus[n] for n in chunk])
                clusters[cid] = {"members": list(chunk), "label": f"{fam} {half}",
                                 "centroid": _unit(vecs), "sealed": False}
                parent_map[cid] = branch
                for n in chunk:
                    parent_map[n] = cid
    leaf_sha = {n: meaning_upfold._text_sha(VERSION, t) for n, t in corpus.items()}
    return {"version": VERSION, "root_id": "", "lens_hash": "stub", "lens_pairs": [],
            "clusters": clusters, "parent_map": parent_map, "leaf_sha": leaf_sha}


@pytest.fixture()
def source(corpus):
    asked: list[str] = []

    def fn(name: str) -> str:
        asked.append(name)
        return corpus[name]

    fn.asked = asked                                                  # type: ignore[attr-defined]
    return fn


@pytest.fixture()
def dsc(tmp_path, tree, source):
    return recursive_read.open_descender(
        tmp_path, backend=StubBackend(), leaf_source=source, tree=tree, allow_test_backend=True)




# ---------------------------------------------------------------------------
# the absence of the write - the only claim left
# ---------------------------------------------------------------------------

def test_a_descent_writes_no_closure_meter_store(dsc, tmp_path):
    """The seam is gone: no store is created, on any fire class, ever."""
    for q in ("alpha query", "beta query", "gamma query"):
        dsc.descend(q, k=5, beam=8)
    assert not (tmp_path / closure_meter.STORE_FILE).exists(), \
        "descend() banked a closure-meter row; the seq 1 cut has regressed"


def test_the_vestigial_fire_argument_still_writes_nothing(dsc, tmp_path):
    """``fire=`` survives only so the four live callers keep parsing. It banks nothing."""
    dsc.descend("alpha query", k=5, beam=8, fire="need")
    dsc.descend("beta query", k=5, beam=8, fire="dutiful")
    assert not (tmp_path / closure_meter.STORE_FILE).exists()
    assert closure_meter.read_rows(tmp_path) == []


def test_recursive_read_does_not_reference_the_meter_at_all(dsc, tmp_path):
    """No import, no bank call, no degrade print left on the descent path."""
    text = Path(recursive_read.__file__).read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines()
                     if "#" not in line and '"""' not in line)
    assert "closure_meter.bank" not in code
    assert "from laplace.engine import closure_meter" not in code


def test_the_meter_fires_no_descent_and_embeds_nothing_of_its_own(dsc, tmp_path, source):
    """The original negative claim, kept: the read path asks the leaf source for nothing extra."""
    before = len(source.asked)
    packet = dsc.descend("alpha query", k=5, beam=8)
    assert packet["hits"], "the descent itself must still work"
    materialized = packet["materialized"]
    assert len(source.asked) - before == materialized, \
        "something asked the leaf source for more than the descent materialized"
