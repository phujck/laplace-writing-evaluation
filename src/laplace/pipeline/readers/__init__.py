"""The reader suite (Phase E, checklist cat 13) — the terminal coherence test.

Ten readers, built as six constructs sharing three organs, plus the human
terminal (R9 Caption-blind and R10 Restart joined the original eight). Conjugate
to the scaffold-wipe: erasure proves no construction debris
survived; the readers prove the OBJECT survives the readers a finished physics
manuscript actually meets.

Public surface Phase F consumes:

    roster / manifests            the declarative spine (who reads, sealed from what,
      ``roster``, ``finding_kinds_manifest``, ``dimension_manifest``,
      ``owned_hard_failures``, ``READERS``, ``HARD_FAILURES``,
      ``READER_FINDING_KINDS``
    invariant checks              ``verify_single_ownership`` (ii), ``verify_kind_partition``
    silence-never-passes          ``reader_verdict_score`` (missing/failed → 0.5)

    R1/R4/R7 sealed-subagent organ   ``sealed.slice_for``, ``sealed.mechanical_floor``,
      ``sealed.pack_for_sealed_read``, ``sealed.parse_sealed_verdict``,
      ``sealed.seal_holds``
    R2 Referee (adversary)           ``referee.pack_for_referee_read``,
      ``referee.referee_floor``, ``referee.parse_referee_verdict``
    R3 Apparatus (mechanical spine)  ``apparatus.read_apparatus`` (runnable now)
    R5/R6 rasteriser organ           ``visual.pack_figure_meaning``,
      ``visual.parse_figure_verdict``, ``visual.figure_floor`` (R5);
      ``visual.pack_geometry``, ``visual.parse_geometry_verdict``,
      ``visual.geometry_floor`` (R6)

Everything is PACKAGE + PARSE (the Phase-D2 pattern): no module calls a model. The
mechanical floors (R3 whole, R1/R4/R7 floors, R5 caption scrub) run every round;
R6's every-round floor is the mechanical panel's log-overfull 'visual' axis (R6
does not re-inspect log-locatable overflow); the sealed/vision/adversary READS are
driven by Phase F at candidate-lock.
"""

# NOTE: the ``roster`` *function* is deliberately NOT re-exported at the package
# level — binding it here would SHADOW the ``roster`` SUBMODULE, so
# ``import laplace.pipeline.readers.roster`` (and the attribute
# ``readers.roster``) would resolve to the function, not the module. Reach the
# function fully-qualified (``from laplace.pipeline.readers.roster import
# roster``) or via the module (``readers.roster.roster``); ``READERS`` is the
# same declarative data most callers want.
from laplace.pipeline.readers.roster import (  # noqa: F401
    HARD_FAILURES,
    READER_FINDING_KINDS,
    READERS,
    SILENT_SCORE,
    Cadence,
    HardFailure,
    Reader,
    ReaderKind,
    dimension_manifest,
    finding_kinds_manifest,
    owned_hard_failures,
    reader_finding,
    reader_verdict_score,
    verify_kind_partition,
    verify_single_ownership,
)
from laplace.pipeline.readers.verdict_io import (  # noqa: F401
    assemble_sidecar,
    build_verdict,
    parse_reply,
    read_verdict,
    write_verdict,
)

__all__ = [
    "READERS", "HARD_FAILURES", "READER_FINDING_KINDS", "SILENT_SCORE",
    "Reader", "HardFailure", "ReaderKind", "Cadence",
    "finding_kinds_manifest", "dimension_manifest",
    "owned_hard_failures", "reader_finding", "reader_verdict_score",
    "verify_single_ownership", "verify_kind_partition",
    "write_verdict", "build_verdict", "parse_reply",
    "read_verdict", "assemble_sidecar",
]
