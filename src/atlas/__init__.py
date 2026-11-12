"""atlas - the record's navigation layer, sealed from the laplace engine.

The governing law (DESIGN_2026-08-01_the-atlas.md §3): the record is the memory; everything
derived from it is a versioned, disposable, measured projection. Phase 1 lands the bottom of
that stack - the immutable snapshot, the segmentation layer that makes a span (never a file)
the unit of retrieval, and the two mechanical seal tests.

The seal remains one-way: this package never imports ``laplace``. At Phase 7 exactly one
Laplace module, ``src/laplace/atlas_bridge.py``, may import this package to construct typed
events and append them through the canonical store. Snapshot export remains a data boundary.
Both directions are enforced by AST walks (``atlas/tests/test_seal.py`` and
``tests/test_atlas_seal.py``); a second Laplace import site is a mechanical failure.

Importing this package has no side effects: no file reads, no model loads, no network.
"""

from __future__ import annotations

from .history import AtlasEvent
from .state import BRIDGE_API_VERSION, PROVIDER_SCHEMA, ConceptricState
from .store import ConceptricStore

__version__ = "0.1.0"

# The bundle-level schema generation. Every derived record also carries its own per-type
# SCHEMA_VERSION (schema.py); this one names the generation the bundle layout belongs to and
# appears in the hashed manifest, so a layout change cannot masquerade as the same snapshot.
ATLAS_SCHEMA_VERSION = "1"

__all__ = [
    "ATLAS_SCHEMA_VERSION",
    "BRIDGE_API_VERSION",
    "PROVIDER_SCHEMA",
    "AtlasEvent",
    "ConceptricState",
    "ConceptricStore",
    "__version__",
]
