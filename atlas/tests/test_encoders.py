"""test_encoders.py - the deterministic pair, the registry's refusals, and the no-model rule.

The last test is the one that keeps the unit suite honest: in a fresh interpreter that imports
the bge adapter, ``fastembed`` must still be absent from ``sys.modules``. A unit run loads no
model, opens no network and takes milliseconds; the moment that assertion fails, some import
moved to module scope and the suite has started paying for ONNX. The reading is taken in a child
process because this one shares an interpreter with the laplace suite, which imports fastembed
for its own reasons - see ``conftest.clean_import_probe``.
"""

from __future__ import annotations

import pytest

from atlas.encoders import ENCODER_NAMES, HashEncoder, SyntheticEncoder, check_contract, get_encoder
from atlas.encoders.base import EncoderRuntimeEvidence, EncoderSpec, unit
from atlas.errors import EncoderContractViolation, EncoderUnavailable

TEXTS = ["alpha mechanism", "beta provenance", "gamma temporal", "delta contradiction",
         "no family word here at all"]


@pytest.fixture(params=[HashEncoder, SyntheticEncoder])
def encoder(request):
    return request.param()


def test_vectors_have_the_declared_dim(encoder):
    vectors = encoder.embed(TEXTS)
    assert len(vectors) == len(TEXTS)
    assert all(len(v) == encoder.dim for v in vectors)


def test_vectors_are_unit_normalised(encoder):
    check_contract(encoder, encoder.embed(TEXTS))
    check_contract(encoder, [encoder.query("a query about mechanism")])


def test_encoding_is_deterministic(encoder):
    assert encoder.embed(TEXTS) == encoder.embed(TEXTS)
    assert encoder.query("same text") == encoder.query("same text")


def test_distinct_texts_get_distinct_vectors(encoder):
    vectors = encoder.embed(TEXTS)
    assert len({tuple(v) for v in vectors}) == len(TEXTS)


def test_empty_input_still_honours_the_contract(encoder):
    vec = encoder.query("")
    assert len(vec) == encoder.dim
    check_contract(encoder, [vec])           # unit, or the zero vector - both are in contract


def test_hash_encoder_returns_zero_for_empty_text():
    """No 3-gram, no direction. Normalising nothing would invent one."""
    assert sum(x * x for x in HashEncoder().query("")) == 0.0


def test_synthetic_encoder_has_a_direction_for_every_string():
    """Its jitter is defined by a hash of the text, so even the empty string lands somewhere.

    Stated rather than fixed: the synthetic geometry exists to give tests real cluster
    structure, and a corpus of empty documents is not a case it needs to model.
    """
    vec = SyntheticEncoder().query("")
    assert abs(sum(x * x for x in vec) - 1.0) < 1e-9


def test_embed_of_nothing_is_nothing(encoder):
    assert encoder.embed([]) == []


def test_encoder_ids_are_distinct_and_stated():
    assert HashEncoder.encoder_id != SyntheticEncoder.encoder_id
    assert "hash" in HashEncoder.encoder_id
    assert "synthetic" in SyntheticEncoder.encoder_id


def test_encoder_spec_and_runtime_evidence_round_trip_exactly():
    spec = EncoderSpec.from_dict(SyntheticEncoder.spec.to_dict())
    evidence = EncoderRuntimeEvidence.exact_single_provider(
        spec,
        "deterministic-python",
        "sha256:" + "3" * 64,
    )

    assert spec == SyntheticEncoder.spec
    assert EncoderRuntimeEvidence.from_dict(evidence.to_dict()) == evidence


def test_runtime_evidence_refuses_a_tampered_verdict():
    evidence = EncoderRuntimeEvidence.exact_single_provider(
        SyntheticEncoder.spec,
        "deterministic-python",
        "sha256:" + "4" * 64,
    ).to_dict()
    evidence["within_tolerance"] = False

    with pytest.raises(EncoderContractViolation, match="verdict does not verify"):
        EncoderRuntimeEvidence.from_dict(evidence)


def test_synthetic_families_land_on_their_own_axis():
    enc = SyntheticEncoder()
    for i, family in enumerate(enc.FAMILIES):
        vec = enc.query(f"a document about {family} things")
        assert vec[i] == max(vec[:4]), family


def test_unit_leaves_the_zero_vector_alone():
    assert unit([0.0, 0.0]) == [0.0, 0.0]
    assert unit([3.0, 4.0]) == [0.6, 0.8]


def test_check_contract_refuses_a_wrong_dim():
    enc = SyntheticEncoder()
    with pytest.raises(EncoderContractViolation) as exc:
        check_contract(enc, [[1.0]])
    assert exc.value.reason == "encoder-contract-violation"


def test_check_contract_refuses_an_unnormalised_vector():
    enc = SyntheticEncoder()
    with pytest.raises(EncoderContractViolation):
        check_contract(enc, [[2.0] + [0.0] * (enc.dim - 1)])


def test_registry_returns_the_deterministic_encoders():
    assert isinstance(get_encoder("hash"), HashEncoder)
    assert isinstance(get_encoder("synthetic"), SyntheticEncoder)
    assert set(ENCODER_NAMES) == {"hash", "synthetic", "bge"}


def test_registry_refuses_an_unknown_name():
    with pytest.raises(EncoderUnavailable) as exc:
        get_encoder("word2vec")
    assert exc.value.reason == "encoder-unavailable"


def test_bge_adapter_refuses_loudly_without_a_model(monkeypatch):
    from atlas.encoders.bge_onnx import MODEL_DIR_ENV, BgeOnnxEncoder
    monkeypatch.delenv(MODEL_DIR_ENV, raising=False)
    enc = BgeOnnxEncoder()
    assert enc.available() is False
    with pytest.raises(EncoderUnavailable) as exc:
        enc.embed(["anything"])
    assert exc.value.reason == "encoder-unavailable"


def test_bge_adapter_requires_a_positive_streaming_batch():
    from atlas.encoders.bge_onnx import BgeOnnxEncoder
    with pytest.raises(ValueError, match="batch_size"):
        BgeOnnxEncoder(batch_size=0)


def test_unit_suite_loads_no_model(clean_import_probe):
    """Importing the bge adapter must not import fastembed. The lazy import is the mechanism.

    Read in a fresh interpreter, not in this one. Both halves of the repository share a process
    (root ``pyproject.toml``, ``testpaths``), and the laplace half imports fastembed for its own
    reasons - fastembed is a base dependency there - so this process's ``sys.modules`` cannot say
    what the adapter's import did. See ``conftest.clean_import_probe``.

    fastembed is an optional extra for atlas, so the probe reports whether it was installed
    rather than requiring it: where it is absent, a module-scope import would raise in the child
    and fail the probe instead of showing up here.
    """
    report = clean_import_probe(
        imports=["atlas.encoders.bge_onnx"],
        watch=["fastembed", "onnxruntime"],
        witness=["fastembed"],
    )
    installed = report["importable"]["fastembed"]
    assert report["loaded"]["fastembed"] is False, f"fastembed installed={installed}"
    assert report["loaded"]["onnxruntime"] is False, f"fastembed installed={installed}"
