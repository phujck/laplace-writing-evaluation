"""errors.py - the refusal vocabulary of the record layer.

Every condition this package cannot honour raises one of these. There is no degrade path
and no fallback: contract clause B.4 says a row whose witness check fails is NOT stored, NOT
downgraded to a weaker kind and NOT retried with a looser predicate, and the charter's
forbidden move 2 rules out any branch that silently substitutes something weaker.

``reason`` is the stable machine-readable identity a test asserts against, following
``atlas.errors``; the message is for a human reading the traceback.
"""

from __future__ import annotations

from ..errors import AtlasError


class WitnessRefused(AtlasError):
    """A row or relation's witness predicate returned False over the stored bytes (B.4)."""

    reason = "witness-refused"


class ClosedColumnViolation(AtlasError):
    """A field outside the declaration's frozen column list, or a declared field absent (B.5)."""

    reason = "closed-column-violation"


class DeclarationFrozen(AtlasError):
    """An attempt to mutate a dataset declaration, alias table or surface set after freezing."""

    reason = "declaration-frozen"


class CpuNumericPathRefused(AtlasError):
    """The numeric core was asked to run on the host. Charter: no CPU numeric path, no fallback."""

    reason = "cpu-numeric-path-refused"


class BlobRewriteRefused(AtlasError):
    """A content blob is written once. A second write under the same handle with other bytes."""

    reason = "blob-rewrite-refused"


class UnknownSurface(AtlasError):
    """A surface form that the frozen surface set / alias table does not declare."""

    reason = "unknown-surface"


class UnknownPredicate(AtlasError):
    """A witness_predicate_id that is not in the frozen registry (B.4, B.9)."""

    reason = "unknown-witness-predicate"


class MalformedSource(AtlasError):
    """The source bytes do not match the container grammar rung (a) declares for them (B.7)."""

    reason = "malformed-source"


class NullSentinelCollision(AtlasError):
    """A real value equal to the column's declared null sentinel - the sentinel cannot separate."""

    reason = "null-sentinel-collision"


class StatusFoldConflict(AtlasError):
    """Raised only by the strict fold entry point; the ingesting fold flags instead (B.32)."""

    reason = "status-fold-conflict"


class DeclarationRefused(AtlasError):
    """A declared dial outside the recipe the declaration itself states (B.5).

    It carries a ``code`` kwarg - ``SEGMENTATION-DIAL-INVALID`` and its siblings - because the
    old store path refuses the same dials BY NAME (``src/atlas/dataset.py:41-44``'s
    ``_require(..., "SEGMENTATION-DIAL-INVALID")``) and a caller that catches this must be able
    to tell which dial refused without reading English. Same rule, same names, on the record path.
    """

    reason = "declaration-refused"
