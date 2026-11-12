"""Durable records: the shared mechanisms every append-only row store uses, with no store's own vocabulary.

  journal  intent-then-execute: act/step/bank/act_end lines, the one stamp law, the closed edge vocabulary (REL)
           and bank_row, the durable append with its journaled begin/done; recover() reads what was in flight
  rows     reading a JSONL store: one dict per line, malformed and non-object lines skipped and counted
  capture  captured incremental reading of one append-only log: suffix reads, replacement detection, exact
           selected rows verified by line hash, and the cut/continuation token codec
  lineage  the one walker over a row graph: declared edges, retrofit edge rows and a scope's legacy dialect

What a store's rows MEAN (work orders, resolutions, which legacy fields imply which relation, which stores
form the engine's graph) belongs to the domain that owns the store: the engine's ledger in laplace.engine.engine_ledger,
Writing's records in laplace.writing.records. The default checkout root is laplace.core.checkout.repo_root; an explicit
root always wins, and the journal's own stores follow LAPLACE_STATE when no root is given. No import-time effects.
"""
