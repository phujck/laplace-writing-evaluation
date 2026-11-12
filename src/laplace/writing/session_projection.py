"""THE SESSION THREAD PROJECTION (M5 readability P2, 2026-10-14): passive read shapes of the writing
conversation, moved out of laplace.web.authoring with no behaviour change.

Purpose. Everything a reader of a writing session gets that is a pure PROJECTION of the immutable journal
records: the bounded thread row (one compact row per turn for the conversation pane, the native session
view=summary read and HTTP /authoring/session?view=summary), the single-turn summary (view=summary on
/authoring/session-turn), the saved reply's presentation text and the session page (full or summary).

Ownership. This module owns no state, lock, cache, token or identity. The journal index (records), its
fold/cache and every identity are laplace.writing.records' and laplace.web.authoring's; the live turn
(_JOBS), child execution, the steering mailbox and the receipt files stay in authoring_surface, which is
also the only HTTP/native door (session_state, session_turn_detail and the facade names below are still
served from there).

Inputs. `source` turn dicts and the `records` index exactly as authoring_surface._records() and
_failure_read_cut() produce them; `reads`, a TurnReads of the owner's body-read callbacks
(proposal/failure/action/application/artifact-link reads); for the page, a continuation view callback
and a lazy rewire index callback.
Outputs. New dicts only: owner objects are never mutated. Cuts apply to the bounded thread row only: SUMMARY_*
are character cuts while shaping it, ROW_* (serialized UTF-8 bytes) bound what the row delivers,
SUMMARY_COLLECTIONS cap collections before shaping and SUMMARY_RESULT_LINKS caps its artifact links; every cut
leaves *_chars / *_total / *_truncated markers and a body_read handle to the exact original. The single-turn
summary keeps complete texts and collections and up to 20 artifact links.
Retention. Nothing is retained between calls.
Consumers. workspace-session.mjs (paintSelection/authorMessage/recorded-turn audit), manuscript-editing.mjs
(fileOnlyManuscriptSelection), workspace.mjs (manuscriptPassageTarget), the child-result reader and the
native session tool, all through authoring_surface's routes.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from laplace.manuscript import source_effects


@dataclass(frozen=True)
class TurnReads:
    """The owner's body reads a turn summary joins (authoring_surface builds one per call)."""
    proposal_view: Callable[..., dict]          # (turn, records=) -> {proposal, proposal_state, ...}
    failure_rows: Callable[..., list]           # (turn, records) -> exact read recovery and related action facts
    failure_view: Callable[..., dict]           # (turn, records) -> the turn with its failure view
    editor_actions: Callable[..., list]         # (turn) -> the turn's editor action rows
    applications: Callable[..., list]           # (turn) -> application rows
    applied_edits: Callable[..., list]          # (turn, application) -> the edits it applied
    artifact_result_links: Callable[..., list]  # (turn, records, actions=, limit=) -> owner artifact links


PUBLIC_MESSAGE_PRESENTATION = 'laplace.writing-public-message-presentation/1'
# THE presentation policy reply_presentation runs (declared by source_contract below): the reply fields it reads, in
# the order it consults them, and every origin it can return, in precedence order. The policy identifier above is
# deliberately unchanged: a message-part basis already seals the presented origin and content digest, so a reply
# whose presentation changed refuses its old pin while every unaffected message keeps its basis.
PRESENTATION_INPUTS = ('display_text', 'proposal', 'text', 'error')
PRESENTATION_ORIGINS = ('display_text', 'proposal.answer', 'structured.answer', 'structured-edit-fallback',
                        'text', 'error', 'structured-empty', 'empty')
# Origins presented in place of a structured raw reply: its raw edit JSON stays at Audit (the exact turn read).
STRUCTURED_ORIGINS = ('structured.answer', 'structured-edit-fallback', 'structured-empty')
# The one generic sentence: only for a structured reply that carries a real edit and no usable answer.
STRUCTURED_EDIT_FALLBACK = 'Proposed manuscript changes are available for review.'


def _structured_reply(text: str) -> dict | None:
    """The public parts of a structured (revise) reply text: its usable answer and whether it carries a real edit.
    None when the text is not a JSON object with an edits list at top level or under proposal. A ```-fenced text is
    unwrapped from the line after its opening fence, so a single-line fence is not recognised."""
    raw=text.strip()
    if raw.startswith('```') and raw.endswith('```'):
        raw=raw.partition('\n')[2].rsplit('```',1)[0]
    try:structured=json.loads(raw)
    except (TypeError,ValueError):return None
    if not isinstance(structured,Mapping):return None
    nested=structured.get('proposal') if isinstance(structured.get('proposal'),Mapping) else {}
    edits=structured.get('edits') if isinstance(structured.get('edits'),list) else nested.get('edits')
    if not isinstance(edits,list):return None
    answer=next((value for value in (structured.get('answer'),nested.get('answer')) if isinstance(value,str) and value),None)
    return {'answer':answer,'edits':any(isinstance(edit,Mapping) and bool(edit) for edit in edits)}


def reply_presentation(reply: Mapping | None) -> dict:
    """One saved reply presentation for human, model history and binding recovery.

    Exact raw reply text remains on the immutable owner row. A repeated terminal
    carrier presents its own answer while referring to the earlier sealed candidate.

    Precedence is PRESENTATION_ORIGINS. A structured (revise) reply presents its own
    public answer; STRUCTURED_EDIT_FALLBACK claims proposed changes only for a real
    edit with no usable answer, never for an empty edits list. display_text wins when not None (an empty string
    included); non-string display_text, text and error values are presented through str().
    """
    reply=reply or {}
    displayed=reply.get('display_text')
    if displayed is not None:return {'text':str(displayed),'origin':'display_text'}
    proposal=reply.get('proposal')
    answer=proposal.get('answer') if isinstance(proposal,Mapping) else None
    if isinstance(answer,str) and answer:return {'text':answer,'origin':'proposal.answer'}
    text=reply.get('text')
    structured=_structured_reply(text) if isinstance(text,str) else None
    if structured is not None:
        # A structured reply shows its own public answer (a reasoned refusal to edit included). The generic
        # sentence claims proposed changes only for a real edit with no usable answer, never an empty list.
        if structured['answer'] is not None:return {'text':structured['answer'],'origin':'structured.answer'}
        if structured['edits']:return {'text':STRUCTURED_EDIT_FALLBACK,'origin':'structured-edit-fallback'}
    elif text:return {'text':str(text),'origin':'text'}
    error=reply.get('error')
    if error:return {'text':str(error),'origin':'error'}
    return {'text':'','origin':'structured-empty' if structured is not None else 'empty'}


def reply_presentation_text(reply: Mapping | None) -> str:
    """The same public text for summaries, model history and exact part reads."""
    return reply_presentation(reply)['text']


# ---- the one bounded-text policy of a thread row (SR2) ----
# Every text a LIST row carries is bounded by exactly one rule: the first N characters,
# plus `<key>_chars` (the original length) and `<key>_truncated` when anything was cut.
# The limits are the policy; the exact originals stay with the single-turn summary and the
# exact turn reads. Nothing here mutates an owner object: every shape below is a new dict.
SUMMARY_TEXT_LIMIT = 2000      # request text, steering text, draft text, selection quote
SUMMARY_REPLY_LIMIT = 4000     # reply display text and the proposal answer fallback (intermediate cut on a bounded row)
# THE THREAD ROW (G15; M5 C7-C9 repair H1, 2026-10-14): the ONE compact row every list reader
# gets (native session view=summary, HTTP /authoring/session view=summary, the conversation
# pane, the child-result reader). A row is a glance: identities, role and admitted settings,
# state and counts, short excerpts with their *_chars/*_truncated markers, the recovery entries,
# and the exact reads (body_read = view=turn, summary_read = view=summary: complete texts,
# selection quote, draft text, every steering row, up to 20 artifact links, usage facts and the
# delivery receipt). The single-turn summary (bounded=False) keeps complete texts: SUMMARY_* widths are only
# the intermediate cut a bounded row is shaped with before ROW_* narrows what the row delivers.
# the ROW_* widths are SERIALIZED UTF-8 BYTES (R1, 2026-10-14): the bytes the excerpt occupies in
# the JSON response (ensure_ascii=False), so a CJK excerpt and a quoted-JSON excerpt (every "
# and \ costs an escape byte, control characters six) count the same way as plain ASCII; the
# *_chars markers keep the complete character count
ROW_TEXT_LIMIT = 120           # request text and the proposal answer fallback on a row (bytes)
ROW_REPLY_LIMIT = 160          # reply excerpt on a row (bytes)
ROW_LINK_DISCOVERY = 21        # the artifact join cap (see _artifact_result_links): a count at the cap is a lower bound
ROW_NOTE_LIMIT = 120           # reply error, draft reason, storage error message on a row (bytes)
ROW_STEERING = 0               # steering rows on a row: none; steering_total counts them (summary_read lists them)
ROW_STEERING_TEXT = 80
ROW_STORAGE_ERRORS = 2
ROW_DROPPED = ("work_basis", "workspace_context", "queued_work_ids", "result_links", "summary_read", "session_id")   # the page's session names the conversation
SUMMARY_NOTE_LIMIT = 500       # draft reason, reply error, storage error messages
SUMMARY_RESULT_LINKS = 3       # artifact links a thread row carries; the rest through the actions read
SUMMARY_COLLECTIONS = {"steering": 5, "undo_entries": 10, "storage_errors": 5, "queued_work_ids": 20}
# Closed shapes (SR2-NESTED). A thread row carries ONLY the fields its consumers read
# (workspace-session.mjs paintSelection/authorMessage/recorded-turn audit, manuscript-
# editing.mjs fileOnlyManuscriptSelection, workspace.mjs manuscriptPassageTarget) plus the
# coordinates, guards and identities those fields address. Nothing unknown is copied at
# any level: the exact record and its read handles already hold the complete data.
SELECTION_EXACT = ("files", "section_ids", "node_id", "node_ids", "line_start", "line_end")
ANCHOR_EXACT = ("file", "repo_file", "binding", "line_start", "line_end", "lines", "section", "section_id",
                "paragraph_id", "block", "node_id", "sha256", "schema_version", "operation_id", "grade", "coarse")
# An anchor's passage texts (quote/before/after/passage_before/passage_after) are read by no
# thread-row consumer; the one passage a row shows is the selection's own bounded `quote`.
# They stay complete in the exact record.
STORAGE_ERROR_EXACT = ("field", "content_handle")


def _scalar_or_list(value):
    """An exact coordinate: a scalar, or a flat list of scalars. Anything deeper is not copied."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)) and all(item is None or isinstance(item, (str, int, float, bool)) for item in value):
        return list(value)
    return None


def _exact_fields(out: dict, value: Mapping, keys) -> None:
    for key in keys:
        if key in value:
            exact = _scalar_or_list(value[key])
            if exact is not None or value[key] is None:
                out[key] = exact


def _bounded_text(out: dict, key: str, value, limit: int) -> None:
    """Write `key` (and chars/truncated) on a NEW dict from any owner value."""
    if value is None:
        return
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    out[key] = text[:limit]
    if len(text) > limit:
        out[key + "_chars"] = len(text)
        out[key + "_truncated"] = True


def _summary_anchor(value) -> dict | None:
    """Closed shape of a source anchor: coordinates/guards/identities exact, no passage texts."""
    if not isinstance(value, Mapping):
        return None
    out: dict = {}
    _exact_fields(out, value, ANCHOR_EXACT)
    return out


def _summary_selection(value) -> dict | None:
    """Closed shape of a request/steering selection: exact coordinates, owned anchor, bounded quote, never a draft."""
    if not isinstance(value, Mapping):
        return None
    out: dict = {}
    _exact_fields(out, value, SELECTION_EXACT)
    if isinstance(value.get("anchor"), Mapping):
        out["anchor"] = _summary_anchor(value["anchor"])
    if isinstance(value.get("quote"), str):
        _bounded_text(out, "quote", value["quote"], SUMMARY_TEXT_LIMIT)
    return out


def _summary_draft(value) -> dict | None:
    """Closed shape of an unsaved draft attachment: status/format exact, owned anchor, text and reason bounded."""
    if not isinstance(value, Mapping):
        return _summary_scalar(value, SUMMARY_TEXT_LIMIT)
    out: dict = {}
    _exact_fields(out, value, ("status", "format"))
    if isinstance(value.get("anchor"), Mapping):
        out["anchor"] = _summary_anchor(value["anchor"])
    _bounded_text(out, "text", value.get("text"), SUMMARY_TEXT_LIMIT)
    _bounded_text(out, "reason", value.get("reason"), SUMMARY_NOTE_LIMIT)
    return out


def _serialized_bytes(text: str) -> int:
    """The bytes `text` occupies inside a JSON string (ensure_ascii=False), without the quotes."""
    return len(json.dumps(text, ensure_ascii=False).encode("utf-8")) - 2


def _clip_utf8(text: str, limit: int) -> str:
    """The longest prefix of `text` whose JSON-serialized UTF-8 form is at most `limit` bytes
    (never splits a character or an escape sequence)."""
    if _serialized_bytes(text) <= limit:
        return text
    used = 0; end = 0
    for index, char in enumerate(text):
        cost = _serialized_bytes(char)
        if used + cost > limit:
            break
        used += cost; end = index + 1
    return text[:end]


def _rebound(out: dict, key: str, limit: int) -> None:
    """Narrow an already bounded text on a row to `limit` UTF-8 bytes: the marker keeps the complete character count."""
    value = out.get(key)
    if not isinstance(value, str):
        return
    chars = out.get(key + "_chars") if isinstance(out.get(key + "_chars"), int) else len(value)
    clipped = _clip_utf8(value, limit)
    if clipped != value:
        out[key] = clipped
        out[key + "_chars"] = chars
        out[key + "_truncated"] = True


def _row_selection(value):
    """A row's selection: coordinates and anchor; the quote is omitted but its length is kept (R2)."""
    if not isinstance(value, Mapping):
        return value
    out = {key: item for key, item in value.items() if not key.startswith("quote")}
    if isinstance(value.get("quote"), str):
        out["quote_chars"] = value.get("quote_chars") if isinstance(value.get("quote_chars"), int) else len(value["quote"])
    return out


def _row_draft(value):
    if not isinstance(value, Mapping):
        return value
    out = {key: item for key, item in value.items() if key != "text"}
    if isinstance(value.get("text"), str):
        out["text_chars"] = value.get("text_chars") if isinstance(value.get("text_chars"), int) else len(value["text"])
        out["text_omitted"] = True   # the words are on summary_read; a row says only that a draft travelled
    _rebound(out, "reason", ROW_NOTE_LIMIT)
    return out


def _thread_row(summary: dict) -> dict:
    """The canonical compact thread row from a bounded single-turn summary (see ROW_* above)."""
    row = {key: value for key, value in summary.items() if key not in ROW_DROPPED}
    _rebound(row, "text", ROW_TEXT_LIMIT)
    _rebound(row, "proposal_answer", ROW_TEXT_LIMIT)
    if "selection" in row:
        row["selection"] = _row_selection(row["selection"])
    if row.get("unsaved_draft") is not None:
        row["unsaved_draft"] = _row_draft(row["unsaved_draft"])
    steering = list(row.get("steering") or [])
    kept = []
    for item in steering[:ROW_STEERING]:
        if not isinstance(item, Mapping):
            kept.append(item); continue
        shaped = dict(item)
        _rebound(shaped, "text", ROW_STEERING_TEXT)
        if "selection" in shaped: shaped["selection"] = _row_selection(shaped["selection"])
        if shaped.get("unsaved_draft") is not None: shaped["unsaved_draft"] = _row_draft(shaped["unsaved_draft"])
        kept.append(shaped)
    row["steering"] = kept
    if row.get("steering_total", len(steering)) > len(kept):
        row["steering_truncated"] = True
    errors = list(row.get("storage_errors") or [])
    row["storage_errors"] = errors[:ROW_STORAGE_ERRORS]
    for item in row["storage_errors"]:
        if isinstance(item, dict): _rebound(item, "message", ROW_NOTE_LIMIT)
    if row.get("storage_errors_total", len(errors)) > len(row["storage_errors"]):
        row["storage_errors_truncated"] = True
    reply = row.get("reply")
    if isinstance(reply, Mapping):
        # the meter facet (usage, provider, model, context window and the selected counter) stays on
        # the row here; session_state keeps it on the newest row only (R2: one qualified meter per
        # page, with its own provider/model so it is never matched against proposed next settings)
        compact = {key: reply[key] for key in ("id", "status", "usage", "provider", "model", "context_tokens_used", "context_window_effective", "context_window_advertised", "usage_basis",
                                               "proposal_carrier", "display_text", "display_text_chars", "display_text_truncated", "error", "error_chars", "error_truncated") if key in reply}
        if isinstance(reply.get("usage_facts_projection"), Mapping):
            facts = reply["usage_facts_projection"]
            compact["usage_facts_projection"] = {key: facts[key] for key in ("schema_version", "selected") if key in facts}
        _rebound(compact, "display_text", ROW_REPLY_LIMIT)
        _rebound(compact, "error", ROW_NOTE_LIMIT)
        row["reply"] = compact
    row["queued_work_ids_total"] = summary.get("queued_work_ids_total", len(summary.get("queued_work_ids") or []))
    if isinstance(row.get("detail"), Mapping):
        row["detail"] = {"turn_id": row["detail"].get("turn_id")}
    # R3: the link join stops at ROW_LINK_DISCOVERY, so a count at the cap is a lower bound; a row
    # carries no links, so "more" means more than discovered, never more than the row shows
    total = row.get("result_links_total") or 0
    if total >= ROW_LINK_DISCOVERY:
        row["result_links_total_basis"] = "at-least"; row["result_links_more"] = True
    else:
        row.pop("result_links_more", None)
    # absence is the glance's zero: null identities, empty collections, zero counts and false
    # flags are omitted (the single-turn summary keeps them); readers treat a missing count as 0
    return {key: value for key, value in row.items()
            if not (value is None or value == [] or value == {} or value is False or (value == 0 and key.endswith(("_count", "_total"))))}


def _summary_scalar(value, limit: int):
    """A text that is not an object: the bounded value plus its own `*_chars` marker on the row."""
    if not isinstance(value, str) or len(value) <= limit:
        return value
    return value[:limit]


def _capped(items, limit: int) -> tuple[list, int, bool]:
    rows = list(items or [])
    return rows[:limit], len(rows), len(rows) > limit


def _summary_steering(row: Mapping) -> dict:
    out = {key: row.get(key) for key in ("id", "ts") if key in row}
    _bounded_text(out, "text", row.get("text"), SUMMARY_TEXT_LIMIT)
    if "selection" in row:
        out["selection"] = _summary_selection(row.get("selection"))
    if row.get("unsaved_draft") is not None:
        out["unsaved_draft"] = _summary_draft(row.get("unsaved_draft"))
    return out


def _summary_reply(reply: Mapping) -> dict:
    """Owned shape of a reply in a thread row: meters, identities and carriers exact; texts bounded; no body."""
    out = {key: copy.deepcopy(reply[key]) for key in
           ("id", "status", "usage", "provider", "model", "context_window_advertised", "context_window_effective",
            "context_tokens_used", "usage_basis", "proposal_carrier", "ts") if key in reply}
    # G15: the row keeps the usage counter the pane reads (the projection's `selected` facet
    # under its schema); the complete usage facts and the delivery receipt projection (3-5 KB
    # per turn on the live edition) belong to the turn read (body_read)
    facts = reply.get("usage_facts_projection")
    if isinstance(facts, Mapping):
        out["usage_facts_projection"] = {key: copy.deepcopy(facts[key]) for key in ("schema_version", "selected") if key in facts}
    _bounded_text(out, "display_text", reply.get("display_text"), SUMMARY_REPLY_LIMIT)
    if reply.get("error") is not None:
        _bounded_text(out, "error", reply.get("error"), SUMMARY_NOTE_LIMIT)
    return out


def _summary_storage_error(value) -> dict:
    """Closed shape of a custody error (writing/bodies.py resolve_fields): field and handle exact, message bounded."""
    out: dict = {}
    if isinstance(value, Mapping):
        _exact_fields(out, value, STORAGE_ERROR_EXACT)
        message = next((value[key] for key in ("message", "error", "detail") if isinstance(value.get(key), str)), None)
        _bounded_text(out, "message", message, SUMMARY_NOTE_LIMIT)
        return out
    _bounded_text(out, "message", value, SUMMARY_NOTE_LIMIT)
    return out


def turn_summary(source: dict, records: dict, *, reads: "TurnReads", bounded: bool = False) -> dict:
    """Conversation text and counts without eager action/proposal bodies.

    ``bounded`` (the session thread page) delivers a LIST row built from owned
    summary shapes under one bounded-text policy (SR2): every text-bearing field
    the projection returns is bounded with ``*_chars``/``*_truncated`` markers:
    request ``text``, ``unsaved_draft.text``/``reason``, ``selection.quote``,
    each steering row's ``text``/``selection.quote``/``unsaved_draft``, the
    reply's ``display_text`` and ``error``, ``proposal_answer`` and every
    ``storage_errors`` message. Nested shapes are closed and recursive: a
    selection carries SELECTION_EXACT plus an owned anchor (ANCHOR_EXACT only; an
    anchor's passage texts are not carried) and a bounded quote; a draft carries status/format, the
    same owned anchor and bounded text/reason; a storage error carries
    field/content_handle and a bounded message. No unknown key is copied at any
    level; the exact record behind ``body_read`` holds the complete data. The
    reply keeps its meters and carriers. ``reply.text`` and ``workspace_context``
    are never carried.
    Collections are capped BEFORE their rows are shaped (SUMMARY_COLLECTIONS and
    SUMMARY_RESULT_LINKS) with ``*_total``/``*_truncated``. Owner objects are
    never mutated: every shape is a new dict. ``body_read`` (view=turn) and
    ``summary_read`` (view=summary) lead to the exact originals; the single-turn
    summary read (``bounded=False``) keeps full texts, collections and up to 20
    links. Both carry the session's ``packet`` and ``role`` (G3).
    """
    turn = dict(source)
    view = reads.proposal_view(turn, records=records)
    reply = turn.get("reply") if isinstance(turn.get("reply"), dict) else None
    proposal = view.get("proposal") if isinstance(view.get("proposal"), dict) else {}
    failures = reads.failure_rows(turn,records)
    actions = reads.editor_actions(turn)
    undo_entries=[]
    for application in reads.applications(turn):
        if not application.get("complete"):continue
        undo_ref=application.get("undo_ref")
        undo_entries.append({"id":application.get("id"),
            "kind":"transaction" if isinstance(undo_ref,dict) else "source-edits",
            "edit_count":len(reads.applied_edits(turn,application)),
            **({"undo_ref":undo_ref} if isinstance(undo_ref,dict) else {}),
            "detail":{"turn_id":turn.get("id"),"view":"application",
                      "item_id":application.get("id")},
            "_order":records.get("orders",{}).get(str(application.get("id")),10**18)})
    for action in actions:
        undo_ref=(action.get("outcome") or {}).get("undo_ref")
        if not isinstance(undo_ref,dict) or any(row.get("undo_ref")==undo_ref for row in undo_entries):continue
        undo_entries.append({"id":action.get("id"),"kind":"transaction","edit_count":0,
                             "undo_ref":undo_ref,
                             "_order":records.get("orders",{}).get(str(action.get("id")),10**18)})
    undo_entries.sort(key=lambda row:(row.pop("_order"),str(row.get("id") or "")))
    result = {key: turn.get(key) for key in
              ("id", "session_id", "project", "text", "mode", "selection",
               "workspace_context", "unsaved_draft", "queued_work_ids", "parent_turn_id", "dispatch_id", "work_id", "work_basis", "provider_settings", "parent_continuation", "reader_profile", "ts")
              if key in turn}
    result_links=reads.artifact_result_links(turn,records,actions=actions)
    result["result_links"]=result_links[:20]
    result["result_links_more"]=len(result_links)>20
    result["result_links_total"]=len(result_links)      # every link the capped join discovered (<= the cap)
    if len(result_links)>20:
        result["result_links_total_basis"]="at-least"   # R3: the join is capped; the actions read lists the rest
    result["steering"] = [{key: row.get(key) for key in
                           ("id", "text", "selection", "workspace_context",
                            "unsaved_draft", "ts") if key in row}
                          for row in turn.get("steering") or []]
    if reply is not None:
        presentation=reply_presentation(reply)
        answer=presentation['text']
        result["reply"] = {key: reply.get(key) for key in
                           ("id", "text", "error", "status", "usage", "provider", "model",
                            "context_window_advertised", "context_window_effective",
                            "context_tokens_used", "usage_basis", "usage_facts_projection", "delivery_receipt_projection", "proposal_carrier", "ts") if key in reply}
        result["reply"]["display_text"]=answer
        if presentation['origin'] in STRUCTURED_ORIGINS:
            # Raw edit JSON stays at Audit, not in the public message body.
            result['reply']['text']=answer
    # A summary links only a stored exact candidate seal. Legacy content digests
    # or historical effect matches cannot manufacture a record/version pin.
    version=(reply or {}).get('proposal_instance_version') if isinstance((reply or {}).get('proposal'),dict) else turn.get('pending_proposal_version')
    basis=(turn.get('proposal_bases') or {}).get(version) or {}
    carrier=(reply or {}).get('proposal_carrier')
    pinned=bool(isinstance(version,str) and version in (turn.get('proposal_versions') or {})
        and isinstance(basis.get('record_id'),str) and basis['record_id']
        and not basis.get('ambiguous_legacy_basis') and turn.get('project') and turn.get('id'))
    if isinstance(carrier,dict):
        pinned=pinned and carrier.get('candidate_version')==version and carrier.get('candidate_record_id')==basis.get('record_id')
    result.update(proposal_version=None,proposal_read_handle=None,proposal_turn_id=None)
    if pinned:
        from laplace.manuscript.proposal_navigation import handle
        result.update(proposal_version=version,proposal_turn_id=turn['id'],
            proposal_read_handle=handle(turn['project'],{'id':turn['id'],'record_id':basis['record_id'],
                'proposal_version':version,'view':'summary'}))
    read_recovery_count=sum(bool((item.get('recovery_read') or {}).get('recovers_read_goal')) for item in failures)
    related_action_count=sum(bool(item.get('related_action')) for item in failures)
    result.update(action_count=len(actions), failure_count=len(failures),
                  read_recovery_count=read_recovery_count, related_action_count=related_action_count,
                  # Legacy aliases count historical attempts with/without read recovery, never tasks.
                  resolved_count=read_recovery_count, unresolved_count=len(failures)-read_recovery_count,
                  proposal_edit_count=len(proposal.get("edits") or []),
                  proposal_state=view.get("proposal_state"),
                  proposal_answer=proposal.get("answer") if proposal.get("edits") else None,
                  undo_entries=undo_entries,
                  storage_errors=list(turn.get("custody_errors") or []),
                  detail={"turn_id": turn.get("id"),
                          "views": ["actions", "failures", "turn"]})
    session = (records.get("sessions") or {}).get(turn.get("session_id")) or {}
    for key in ("packet", "role"):
        if session.get(key) not in (None, ""):
            result[key] = session[key]
    project, ident = turn.get("project"), turn.get("id")
    if project and ident:
        from urllib.parse import urlencode
        read = lambda view: {"http": {"method": "GET", "url": "/authoring/session-turn?" + urlencode({"project": project, "id": ident, "view": view})}}
        result["body_read"] = read("turn")
        result["summary_read"] = read("summary")
    if bounded:
        result.pop("workspace_context", None)
        # Texts the row carries directly.
        for key, limit in (("text", SUMMARY_TEXT_LIMIT), ("proposal_answer", SUMMARY_REPLY_LIMIT)):
            value = result.pop(key, None)
            if value is not None:
                _bounded_text(result, key, value, limit)
        if "selection" in result:
            result["selection"] = _summary_selection(result.get("selection"))
        if result.get("unsaved_draft") is not None:
            result["unsaved_draft"] = _summary_draft(result.get("unsaved_draft"))
        # Collections are capped before their rows are shaped.
        steering, total, cut = _capped(turn.get("steering") or [], SUMMARY_COLLECTIONS["steering"])
        result["steering"] = [_summary_steering(row) for row in steering if isinstance(row, Mapping)]
        result["steering_total"] = total
        if cut: result["steering_truncated"] = True
        rows, total, cut = _capped(undo_entries, SUMMARY_COLLECTIONS["undo_entries"])
        result["undo_entries"] = rows; result["undo_entries_total"] = total
        if cut: result["undo_entries_truncated"] = True
        rows, total, cut = _capped(turn.get("custody_errors") or [], SUMMARY_COLLECTIONS["storage_errors"])
        result["storage_errors"] = [_summary_storage_error(row) for row in rows]; result["storage_errors_total"] = total
        if cut: result["storage_errors_truncated"] = True
        rows, total, cut = _capped(turn.get("queued_work_ids") or [], SUMMARY_COLLECTIONS["queued_work_ids"])
        result["queued_work_ids"] = rows; result["queued_work_ids_total"] = total
        if cut: result["queued_work_ids_truncated"] = True
        # G15: a row's artifact link carries what the pane reads (the owner url, path, scope,
        # receipt and pin, the aliases that match markdown links); the duplicate http block
        # and the basis sentence stay on the turn read
        result["result_links"] = [{key: link[key] for key in ("project", "path", "scope", "expected_sha256", "owner", "artifact_id", "url", "action_id", "turn_id", "aliases") if key in link}
                                  if isinstance(link, Mapping) else link for link in result_links[:SUMMARY_RESULT_LINKS]]
        result["result_links_total"] = len(result_links)
        result["result_links_more"] = len(result_links) > SUMMARY_RESULT_LINKS
        if isinstance(result.get("reply"), dict):
            # The thread shows an excerpt of the answer; the exact body is one read away.
            result["reply"] = _summary_reply(result["reply"])
        return _thread_row(result)
    return result

def session_page(selected_turns: list, records: dict, session: Mapping, *, view: str, reads: TurnReads,
                 continuation: Callable[[dict], dict], rewire_index: Callable[[str], dict]) -> tuple[list, dict | None]:
    """The turns of one session page, newest last: `view` "summary" gives bounded thread rows, "full" the
    exact public turns with their actions, applications and proposal view. Returns (page, newest), where
    newest is the summary row that carries the page's single usage meter (None for "full" or when no row
    has one). `continuation` resolves a parent continuation for display; `rewire_index(project)` is read
    only when a legacy concept_change receipt has to be shown by its canonical subject."""
    page = []
    for source in selected_turns:
        source = continuation(source)
        if view == "summary":
            page.append(turn_summary(source, records, reads=reads, bounded=True)); continue
        turn = reads.failure_view(source, records)
        actions = reads.editor_actions(turn)
        if isinstance(turn.get('application'), dict):
            turn['application'] = {**turn['application'], 'edits': reads.applied_edits(turn, turn['application'])}
        turn.pop('proposal_versions', None)
        # Early action receipts identified the rewire receipt instead of its
        # semantic subject. Resolve that existing authority for display without
        # rewriting the immutable action history.
        for action in actions:
            outcome = dict(action.get('outcome') or {})
            identities = list(outcome.get('identities') or [])
            legacy = [value for value in identities if isinstance(value, str) and value.startswith('RW-')]
            if action.get('operation') == 'concept_change' and legacy:
                indexed = rewire_index(turn['project'])
                subjects = []
                for receipt_id in legacy:
                    record = indexed.get(receipt_id) or {}
                    subjects.extend(record[key] for key in ('node', 'target') if record.get(key))
                if subjects:
                    outcome.update(identities=list(dict.fromkeys(subjects + [x for x in identities if x not in legacy])),
                                   receipts=list(dict.fromkeys(list(outcome.get('receipts') or []) + legacy)),
                                   display_resolution='canonical rewire subjects')
                    action['outcome'] = outcome
        turn["actions"] = actions
        turn.update(reads.proposal_view(turn, records=records))
        if isinstance(turn.get("reply"), dict):
            turn["reply"] = {**turn["reply"], "actions": actions}
        page.append(turn)
    newest = None
    if view == "summary":
        # the page carries the usage meter once, on the newest row that has one (the pane reads
        # the latest reply's usage); every row's own meter is on its body_read
        newest = next((row for row in reversed(page) if isinstance(row.get("reply"), dict) and ("usage" in row["reply"] or "usage_facts_projection" in row["reply"])), None)
        METER = ("usage", "usage_facts_projection", "provider", "model", "context_tokens_used", "context_window_effective", "context_window_advertised", "usage_basis")
        # admitted settings travel on the newest row and on any row whose admitted settings differ
        # from the session's; a row equal to the session's settings says so by absence
        session_settings = {key: session.get(key) for key in ("provider", "model", "effort")}
        last = page[-1] if page else None
        for row in page:
            if row is not newest and isinstance(row.get("reply"), dict):
                row["reply"] = {key: value for key, value in row["reply"].items() if key not in METER}
            settings = row.get("provider_settings")
            if row is not last and isinstance(settings, Mapping) and {key: settings.get(key) for key in ("provider", "model", "effort")} == session_settings and set(settings) <= {"provider", "model", "effort"}:
                row.pop("provider_settings", None)
    return page, newest


# ---------------------------------------------------------------- the editor's actions of one turn
# The turn's tool actions joined to the applications they produced (moved from authoring_surface, family 2).

def editor_actions(turn: dict) -> list[dict]:
    actions = []
    applications = source_effects.applications(turn)
    for original in turn.get('tool_actions', []):
        action = {**original, 'outcome': dict(original.get('outcome') or {})}
        if action.get('operation') == 'apply_revision':
            ids = set(action['outcome'].get('identities', [])) | set(action['outcome'].get('receipts', []))
            application = next((row for row in applications if row.get('id') in ids), None)
            if application:
                action['outcome'].update(application_id=application['id'], turn_id=turn['id'],
                    proposal_version=next((row.get('proposal_version') for row in turn.get('proposal_decisions', [])
                        if row.get('application_id')==application['id']), application.get('proposal_sha256')),
                    edits=source_effects.applied_edits(turn, application))
        actions.append(action)
    linked = {action['outcome'].get('application_id') for action in actions}
    for application in applications:
        if not application.get('complete') or application.get('id') in linked:
            continue
        edits = source_effects.applied_edits(turn, application)
        if not edits:
            continue
        actions.append({'id': application.get('id'), 'ts': application.get('ts'),
                        'operation': 'apply_revision', 'outcome': {
                            'status': 'SUCCEEDED', 'views': ['manuscript'],
                            'application_id': application['id'], 'turn_id': turn['id'],
                            'proposal_version': next((row.get('proposal_version') for row in turn.get('proposal_decisions', [])
                                if row.get('application_id')==application['id']), application.get('proposal_sha256')),
                            'edits': edits,
                            'paths': list(dict.fromkeys(edit['file'] for edit in edits)),
                            'receipts': [application['id']]}})
    for change in turn.get('native_actions', []):
        actions.append({"operation": "native_file_change", "outcome": {
            "status": "SUCCEEDED", "views": ["manuscript", "document"],
            "paths": [change.get("path")], "revisions": {}, "receipts": [],
            "native": True, "change_kind": change.get("kind")}})
    return actions


# ---------------------------------------------------------------- the declared operation

def source_contract() -> dict:
    """Owner-authored meaning of reply_presentation (domain.authoring): pure and stable, its facts computed from the
    policy constants the function and its summary consumer run. No journal, body store or live kernel is read."""
    from laplace.work import source_contracts as SC
    here = 'src/laplace/writing/session_projection.py'
    segments = {
        'purpose': {'question': 'What public text does one saved reply show?',
            'meaning': 'One presentation of a saved reply, shared by the conversation summary, model history, session migration '
                       'and the exact public message-part read. The presented text is a saved public field (display_text, '
                       'proposal.answer, text or error), the answer parsed from a recognised structured reply, the fixed '
                       'application-authored fallback sentence, or empty. It never rewrites the saved reply '
                       'row, its instruction or its raw text, and never exposes provider reasoning, usage or workspace context. '
                       'Edit bodies are hidden only for a recognised structured reply; any other text is shown as saved.'},
        'inputs': {'fields': list(PRESENTATION_INPUTS), 'proposal_fields': ['answer'],
            'structured_text': {'fence': 'A stripped text that starts and ends with ``` is unwrapped to its lines after the opening fence '
                         'line and before the last ```; a single-line fenced text has no such lines and is not recognised.',
                'recognised': 'The whole (unwrapped) text parses as a JSON object with an edits list at top level or under proposal.',
                'answer': 'The top-level answer, else proposal.answer; only a non-empty string is usable.',
                'real_edit': 'At least one non-empty object in that edits list.'},
            'plain': 'Malformed JSON, non-object JSON, JSON whose edits value is not a list, JSON with surrounding prose '
                     'and a single-line fence are not recognised: they are shown verbatim as text, any edit JSON included.',
            'coercion': 'A non-string display_text, text or error is presented through str().'},
        'precedence': {'origins': list(PRESENTATION_ORIGINS),
            'rules': ['display_text, when not null (an intentional empty string included), wins; a non-string through str().',
                      'Otherwise a non-empty string proposal.answer.',
                      'Otherwise a recognised structured text presents its usable answer; with none and a real edit, the fixed fallback sentence.',
                      'Otherwise a truthy unrecognised text as saved (str() for a non-string).',
                      'Otherwise a truthy saved error (str() for a non-string).',
                      'Otherwise empty: structured-empty for a recognised structured text with neither answer nor real edit, else empty.']},
        'fallback': {'text': STRUCTURED_EDIT_FALLBACK, 'chars': len(STRUCTURED_EDIT_FALLBACK),
            'origin': 'A fixed sentence authored by the application, not saved reply text.',
            'claims': 'A recognised structured reply carries a real edit and no usable answer.',
            'never': ['an empty edits list', 'a structured reply with a usable answer']},
        'nonmutation': {'returns': 'a new {text, origin} mapping', 'reads_only': list(PRESENTATION_INPUTS),
            'summary': 'turn_summary replaces only its own copy of reply.text for the structured origins; the saved row and the '
                       'exact turn read (Audit) keep the raw text.',
            'origins_replacing_text': list(STRUCTURED_ORIGINS)},
        'authority': {'kind': 'pure read projection', 'grants': [],
            'not_authority': ['display text', 'a proposal answer', 'a structured answer', 'the generic sentence'],
            'meaning': 'Presented text is a saved public field, a derived structured answer, the fixed fallback sentence or empty. '
                       'It is not a proposal, an applied edit or a review, and selecting it grants no proposal, apply or review authority.'},
        'currentness': {'policy': PUBLIC_MESSAGE_PRESENTATION,
            'basis': 'session_reads.public_message seals presentation_policy, presentation_origin and content_sha256 with the '
                     'source, session and turn row pins.',
            'stale': 'A changed presented text or origin changes the basis: an older pinned page refuses CHANGED_MESSAGE.',
            'unchanged': 'A message whose presented text and origin are unchanged keeps its basis.',
            'raw_row': 'A presentation change leaves the source row pin unchanged.'},
        'recovery': {'refusal': 'CHANGED_MESSAGE', 'restart': 'restart_read: offset 0 without a pin, requalified explicitly.',
            'raw': 'audit_read (view=turn) returns the exact saved reply, structured raw text included.'},
        'bounds': {'single_turn_summary': 'turn_summary(bounded=False) carries the complete presented text; this module applies no cut.',
            'thread_row': {'shaping_cut_chars': SUMMARY_REPLY_LIMIT, 'delivered_utf8_bytes': ROW_REPLY_LIMIT,
                'meaning': 'turn_summary(bounded=True) first cuts display_text to the shaping width (intermediate only); the row '
                           'then delivers at most the delivered width in serialized UTF-8 bytes (ensure_ascii=False, escapes counted, '
                           'never splitting a character), with display_text_chars (the complete length) and display_text_truncated '
                           'when cut. The complete presented text is read through the single-turn summary or the public message part.'},
            'public_message': 'Paging of the complete presented text belongs to session_reads.public_message (a reply part '
                              'defaults to 4000 characters per page, at most 40000).'}}
    relations = [{'consumer': 'kernel.declared-source', 'relation': 'projects', 'segments': list(segments),
                  'location': 'src/laplace/engine/source_kernel_input.py'}]
    for consumer, relation, names, location in [
            ('writing.session_projection.reply_presentation', 'implements', ['inputs', 'precedence', 'fallback', 'nonmutation'], here),
            ('writing.session_projection.turn_summary', 'consumes', ['precedence', 'fallback', 'nonmutation', 'bounds'], here),
            ('writing.session_reads.public_message', 'consumes', ['inputs', 'precedence', 'fallback', 'currentness', 'recovery'],
             'src/laplace/writing/session_reads.py'),
            ('writing.tool_sessions.conversation_history', 'consumes', ['precedence', 'fallback'], 'src/laplace/writing/tool_sessions.py'),
            ('writing.turn_context._migration_history', 'consumes', ['precedence', 'fallback'], 'src/laplace/writing/turn_context.py'),
            ('tests.public_message_parts', 'evaluates', ['inputs', 'precedence', 'fallback', 'nonmutation', 'currentness', 'recovery'],
             'tests/test_public_message_parts.py'),
            ('tests.public_message_http_contract', 'evaluates', ['currentness', 'recovery'], 'tests/test_public_message_http_contract.py'),
            ('tests.session_projection', 'evaluates', ['precedence', 'fallback', 'nonmutation', 'bounds'], 'tests/test_session_projection.py')]:
        relations.append({'consumer': consumer, 'relation': relation, 'segments': names, 'location': location})
    steps = [dict(zip(('id', 'primitive', 'object', 'effect', 'guard'), row)) for row in (
        ('display', 'session_projection.reply_presentation', 'display_text', 'none', 'present, empty included'),
        ('proposal', 'session_projection.reply_presentation', 'proposal.answer', 'none', 'non-empty string'),
        ('structured', 'session_projection._structured_reply', 'structured text', 'none', 'JSON object with an edits list'),
        ('text', 'session_projection.reply_presentation', 'text', 'none', 'not structured, non-empty'),
        ('error', 'session_projection.reply_presentation', 'error', 'none', 'non-empty'))]
    return SC.validate(SC.detached({'schema': SC.SCHEMA, 'owner': 'domain.authoring', 'operation': 'reply_presentation',
        'purpose': {'text': 'Present one saved reply as public text without rewriting it or claiming proposed changes it does not carry.',
                    'assumptions': ['The saved reply row is immutable; presentation is recomputed on every read.',
                                    'A structured reply is the provider revise shape {answer, edits}.']},
        'segments': segments, 'relations': relations, 'steps': steps,
        'authority': segments['authority'], 'recovery': segments['recovery']}))
