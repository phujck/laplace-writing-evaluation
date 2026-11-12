"""The writing organ: manuscript generation as a state machine over reader knowledge.

Design: DESIGN_2026-08-07_the-writing-organ.md. Three limbs:
  belief  - movement-scale generation against a contract (clustering stage, WO-20260807-011500-000001)
  doubt   - residue readers that never touch prose: the bounded prefix reader (reader.py),
            the bidirectional fill-in (WO-20260807-011500-000002), the claim auditor (auditor.py)
  desire  - the content contract and computed line: claim graph, epistemic types, ordering (line.py)

Judgment is comparative (tournament.py), anchored on exemplars, and benched on known
defects before it is trusted on unknown ones. The default repair is deletion.
"""

from laplace.pipeline.writing_organ.schema import Claim, Finding, MovementContract, ReaderState
