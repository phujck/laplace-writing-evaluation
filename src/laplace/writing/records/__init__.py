"""One writing-journal read owner: indexes, exact rows and derived folds.

Journal banking/sealing is ``records._bank`` (``bank``); source effects and live provider controls stay upstream.
Metadata, rich and Activity project views keep their existing distinct lifetimes.
"""
from ._index import (AmbiguousRecord,MetadataIndex,index,exact_record,artifact_record,selected_journal,selected_journal_fields,accepted_link_candidates,recorded_source_file,
    _LOCK as index_lock,_INDEXES as indexes,
    _snapshot as snapshot,_dispatch_metadata_cut as dispatch_metadata_cut)
from ._fold import (_records as fold_records,_fold_record as fold_record,
    _dispatch_records as dispatch_records,_proposal_digest as proposal_digest,
    _proposal_effect_digest as proposal_effect_digest,
    _canonical_read_payload as canonical_read_payload,
    _session_display_title as session_display_title)
from ._bank import (bank,prepare_custody_row,proposal_write_lock,author_update_delivery_lock,turn_context_basis)
from ._failures import selected_failure_records


def raw_indexed_record(idx, meta):
    """Public selected-row route; the index owns verification and invalidation."""
    return _index._raw_indexed_record(idx, meta)


def source_execution_metadata(root, project, commission_id):
    """One commission's incremental bounded headers; never hydrate transcript/body custody."""
    idx=index(root)
    return idx, list(idx.by_source_commission.get((project,commission_id),()))
