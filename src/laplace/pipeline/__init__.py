"""The pipeline package — the conceptric→storyboard→projection machinery, generic.

There is one thing: every act enters by reconstruction — local views of a global
conceptric. This package is that law as code for the generation pipeline:

- :mod:`laplace.pipeline.schema`   — every record shape / op vocabulary, stated once
- :mod:`laplace.pipeline.registry` — every project path, resolved through one door
- :mod:`laplace.pipeline.ledger`   — the one append-only engine (+freeze/transaction)
- :mod:`laplace.pipeline.evolve`   — execute an evolution contract (both directions)
- :mod:`laplace.pipeline.restructure` — restructure(project, target_arc)
- :mod:`laplace.pipeline.propagate`   — minimal dirty set + the typed worklist
- :mod:`laplace.pipeline.dispatch`    — compile_dispatch: the ONLY agent-prompt path

Import submodules directly (``from laplace.pipeline import schema``); this
package initialiser stays empty so the leaf ``schema`` module can be consumed by
``corpus_ingest``/``storyboard`` without a cycle through the heavier siblings.
"""
