"""The Laplace Engine: a cross-LLM, self-refining drafting canon served over MCP.

The engine exposes the tripartite task loop - orient (understand the goal and load
relevant canon), execute (translate the goal into a local action), and verify
(translate the result back and check consistency) - plus a slow self-refinement
loop (assess + dream) governed by measured skill fitness.
"""

# The package root imports nothing: every owner is reached by its own module (laplace.system describes them).
# It used to re-export laplace.pipeline.canon.Canon/canon_root, which loaded the canon on every laplace import; no
# consumer used the root spelling (measured 2026-10-20), so they are reached as laplace.pipeline.canon only.
