"""The editor's doors as verb x concept, with `expected` and a resolver that resolves.

WRITING-CONSOLIDATION-W1, packet `editor-doors`.  Every proof here is behavioural on a
throwaway manuscript tree: a request goes in, a banked row or a refusal comes out, and the
refusal's own `needed` is fed straight back in.  Nothing asserts that a comment exists in the
source.

What is proved, in order:

1. THE ONE REQUEST SHAPE.  A grammar-shaped body (`{verb, concept, target, expected, payload}`)
   and the old flat body reach the SAME executor and bank the same row, because the grammar
   body is rewritten into the owner's spelling and `adjudicate` runs once (GRAMMAR.md section 6
   rule 1).  This is what makes differential replay of the recorded corpus sound: there is one
   code path under two spellings.
2. THE RESOLVER RESOLVES.  A stale token is refused with `refused.needed`, and
   `{**request, **needed}` applies.  Not "a refusal is returned" --- the retry is performed.
3. THE READ PUBLISHES WHAT THE DOOR COMPARES.  The token `walk.doc(identities=True)` puts on a
   block is byte-identical to the token the door's own gate mints for that span, so a surface
   can never send a token the door was never going to accept.
4. NO CLOBBER.  A request carrying the CURRENT token and DIFFERENT text re-splices the author's
   own passage into the current bytes, and writes nothing at all when that passage is not
   locatable exactly once.  This state only exists because the door now accepts tokens, so the
   proof exists in the same packet as the feature.
5. THE RULING IS ON THE EXISTING ROW KIND, and reaches a session through the read the `note`
   home already declares.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from laplace.core import grammar as g
from laplace.core import identity_doors
from laplace.manuscript import review_surface as rv
from laplace.web import review_http
from laplace.manuscript import walk
from laplace.native import verbs as wv
from laplace.pipeline.ledger import read_jsonl

pytestmark = pytest.mark.unit

_MAIN = ("\\documentclass{article}\n\\begin{document}\n"
         "\\input{N1}\n\\end{document}\n")
_N1 = (
    "% PLAN:N1\n"
    "\\section{Introduction}\\label{sec:N1}\n"
    "\n% N1-p1\n"
    "The quick brown fox jumps over the lazy dog.\n"
    "\n% N1-p2\n"
    "The lazy dog sleeps here in the afternoon sun.\n"
)
#: the 1-based inclusive span of the `% N1-p1` paragraph's own line --- the marker is
#: MACHINE-OWNED and outside the span, which is the convention the canvas's block model and
#: `fragment_view` both use, and what the `prose` home digests.
_P1_SPAN = (5, 5)
_P1_TEXT = "The quick brown fox jumps over the lazy dog."


def _md(tmp_path: Path) -> Path:
    md = tmp_path / "ms"
    md.mkdir(parents=True)
    (md / "main.tex").write_text(_MAIN, encoding="utf-8")
    (md / "N1.tex").write_text(_N1, encoding="utf-8")
    (md / "feedback").mkdir()
    return md


def _owned_adjudicate(md: Path, project: str, payload: dict, **kwargs):
    """RD-EDITOR-ROOT: these legacy unregistered fixtures name the disposable checkout that owns their
    manuscript directory (`<root>/ms`), exactly as a real caller names its root; the owner refuses a source
    outside the root it admitted before any effect."""
    return rv.adjudicate(md, project, payload, repo_root=Path(md).parent, **kwargs)


def _rows(md: Path) -> list[dict]:
    p = md / "feedback" / "feedback.jsonl"
    return read_jsonl(p) if p.is_file() else []


def _prose_token(project: str, file_rel: str, start: int, end: int, text: str) -> str:
    return str(g.mint("prose", "%s::%s:%d-%d" % (project, file_rel, start, end),
                      g.digest_bytes(text.encode("utf-8"))))


# --------------------------------------------------------------------------- #
# 1. One request shape, one executor
# --------------------------------------------------------------------------- #
def test_the_grammar_body_and_the_old_body_bank_the_same_row(tmp_path):
    """Two spellings, one code path.  The rows differ only in their id and timestamp."""
    old = _owned_adjudicate(_md(tmp_path / "a"), "proj", {
        "verb": "comment", "by": "author", "section": "N1", "paragraph": "N1-p1",
        "coarse": False, "comment": "the opener hedges", "disposition": "rework",
        "file": "N1.tex", "line_start": _P1_SPAN[0], "line_end": _P1_SPAN[1]})
    md = _md(tmp_path / "b")
    request = wv.grammar_request(
        {"concept": "note@paragraph", "by": "author",
         "target": "proj::N1.tex:%d-%d" % _P1_SPAN,
         "payload": {"section": "N1", "paragraph": "N1-p1", "coarse": False,
                     "comment": "the opener hedges", "disposition": "rework"}},
        name="review/adjudicate-comment")
    assert (request.verb, request.concept) == ("create", "note@paragraph")
    body = review_http._owner_adjudication(request, {"corpus": "proj"})
    assert body["verb"] == "comment", "the shim restores the executor's own discriminator"
    assert (body["file"], body["line_start"], body["line_end"]) == ("N1.tex", *_P1_SPAN), \
        "the file and the span are read off the request's target, not repeated in the payload"
    new = _owned_adjudicate(md, "proj", body)
    for res in (old, new):
        assert res["ok"] is True and res["grade"] == "paragraph"
    # NOTHING differs but the id and the timestamp (WRITING-CONSOLIDATION-W1, the synthesis's
    # stored-key audit). An earlier draft of this packet banked `altitude_source` beside the
    # altitude and this test allowed for it; the key had no reader in the product and did not
    # record what it was described as recording (`_comment_altitude` answers `named` whenever
    # the caller names an altitude, which the editor's own gesture always does), so it is
    # removed rather than kept and this assertion is the whole comparison.
    assert "altitude_source" not in old["record"]["anchor"]
    assert "altitude_source" not in new["record"]["anchor"]
    assert old["record"]["anchor"]["altitude"] == new["record"]["anchor"]["altitude"] == "paragraph"
    drop = {"id", "ts"}

    def _bare(record):
        return {k: v for k, v in record.items() if k not in drop}

    assert _bare(old["record"]) == _bare(new["record"])


def test_a_body_without_a_concept_is_not_a_grammar_request(tmp_path):
    """The discriminator is `concept` and nothing else, so no recorded row of the corpus ---
    none of which carries one --- can enter the new branch."""
    assert wv.grammar_request({"verb": "rewrite", "before": "x"},
                              name="review/adjudicate") is None
    assert wv.grammar_request({}, name="review/adjudicate") is None


def test_the_door_knows_its_act_from_the_table_and_not_from_itself():
    assert wv.http_act("review/adjudicate") == ("change", "prose@paragraph", "paragraph")
    assert wv.http_acts("review/adjudicate-comment") == (
        ("create", "note@paragraph"), ("create", "note@section"), ("create", "note@chapter"))
    for name in ("authoring/section-change", "authoring/block-change",
                 "authoring/structural-undo", "authoring/apply",
                 "authoring/proposal-decision"):
        verb, concept, altitude = wv.http_act(name)
        assert verb in g.VERBS and g.concept_altitude(concept) == altitude
    with pytest.raises(KeyError):
        wv.http_act("authoring/not-a-door")


# --------------------------------------------------------------------------- #
# 2. The resolver resolves: refused -> needed -> retried -> applied
# --------------------------------------------------------------------------- #
def _comment(md, **extra):
    payload = {"verb": "comment", "by": "author", "section": "N1", "paragraph": "N1-p1",
               "coarse": False, "comment": "cut this", "disposition": "cut",
               "altitude": "paragraph", "file": "N1.tex",
               "line_start": _P1_SPAN[0], "line_end": _P1_SPAN[1]}
    payload.update(extra)
    return _owned_adjudicate(md, "proj", payload)


def test_a_stale_ruling_is_refused_and_the_needed_token_is_the_whole_cure(tmp_path):
    md = _md(tmp_path)
    stale = _prose_token("proj", "N1.tex", *_P1_SPAN, "a passage that is not there")
    refused = _comment(md, expected=[stale])
    assert "refused" in refused and refused["refused"]["kind"] == "identity-stale"
    assert _rows(md) == [], "a refused ruling banks nothing"
    needed = refused["refused"]["needed"]
    assert needed["expected"], "the refusal serves the current token"
    # THE RETRY, performed: `{**request, **refused.needed}` and nothing else.
    applied = _comment(md, **needed)
    assert applied["ok"] is True
    assert needed["expected"] == [
        _prose_token("proj", "N1.tex", *_P1_SPAN, _P1_TEXT)], \
        "the token served is the token of the addressed span's own bytes"
    assert len(_rows(md)) == 1


def test_a_current_token_is_accepted_and_the_ruling_rides_the_existing_row_kind(tmp_path):
    md = _md(tmp_path)
    token = _prose_token("proj", "N1.tex", *_P1_SPAN, _P1_TEXT)
    res = _comment(md, expected=[token])
    assert res["ok"] is True
    row = _rows(md)[-1]
    assert row["kind"] == "comment", "no new row kind"
    assert row["anchor"]["disposition"] == "cut"
    assert row["anchor"]["altitude"] == "paragraph"
    assert "altitude_source" not in row["anchor"], "the derivable key is not stored"
    assert "disposition" not in row, "the ruling rides the anchor, not a new top-level key"


def test_a_ruling_with_no_container_refuses_a_token_instead_of_ignoring_it(tmp_path):
    """A whole-paper deposit has no one home, so a token sent with one is `unknown-home`.
    Silently dropping it is the failure: the caller would believe it had been compared."""
    md = _md(tmp_path)
    res = _owned_adjudicate(md, "proj", {
        "verb": "comment", "by": "author", "grade": "artefact", "comment": "the arc is wrong",
        "disposition": "rework", "expected": [_prose_token("proj", "N1.tex", 4, 5, "x")]})
    assert res["refused"]["kind"] == "unknown-home"
    assert _rows(md) == []


def test_the_three_altitudes_prove_three_different_homes(tmp_path):
    md = _md(tmp_path)
    whole = (md / "N1.tex").read_text(encoding="utf-8")
    for altitude, kind, text, span in (
            ("paragraph", "prose", _P1_TEXT, _P1_SPAN),
            ("section", "section", whole, None),
            ("chapter", "chapter", whole, None)):
        assert identity_doors.COMMENT_CONTAINER[altitude] == kind
        home_id = ("proj::N1.tex:%d-%d" % span) if span else "proj::N1.tex"
        token = str(g.mint(kind, home_id, g.digest_bytes(text.encode("utf-8"))))
        res = _comment(md, altitude=altitude, expected=[token])
        assert res["ok"] is True, (altitude, res)
        assert _rows(md)[-1]["anchor"]["altitude"] == altitude
        # ... and the same request with a stale token of that home is refused
        bad = str(g.mint(kind, home_id, g.digest_bytes(b"moved")))
        assert _comment(md, altitude=altitude, expected=[bad])["refused"]["kind"] \
            == "identity-stale", altitude


# --------------------------------------------------------------------------- #
# 3. The read publishes exactly what the door compares
# --------------------------------------------------------------------------- #
def test_the_fragment_read_publishes_the_token_the_comment_door_accepts(tmp_path):
    md = _md(tmp_path)
    view = rv.fragment_view(md, "N1", "N1-p1", "proj")
    assert view["ok"] is True
    assert (view["line_start"], view["line_end"]) == _P1_SPAN
    # the home is addressed MANUSCRIPT-relative, which is what the splice doors compare; the
    # read says so in its own payload rather than leaving a caller to guess between two paths
    assert view["manuscript_file"] == "N1.tex" and view["file"].endswith("/N1.tex")
    homes = view["identities"]
    token = homes["prose:proj::N1.tex:%d-%d" % _P1_SPAN]
    assert _comment(md, expected=[token])["ok"] is True
    # the section and chapter homes are the file's bytes, published together because a
    # request carries exactly one of them and a caller that must ask twice sends the wrong one
    assert g.parse(homes["section:proj::N1.tex"]).digest \
        == g.parse(homes["chapter:proj::N1.tex"]).digest, \
        "one file's bytes, two home kinds the grammar declares over them; each token names " \
        "its own home, which is why this is not a second name for one value"
    assert _comment(md, altitude="section",
                    expected=[homes["section:proj::N1.tex"]])["ok"] is True


def test_the_canvas_publishes_the_token_the_rewrite_door_compares(tmp_path, monkeypatch):
    """`walk.doc(identities=True)` mints over `blk["tex"]`; the door mints over the file's own
    lines at the same span.  The two must be the same string or the editor is sending a token
    the door was never going to accept."""
    md = _md(tmp_path)
    monkeypatch.setattr(walk, "_repo_root", lambda: tmp_path)
    # `walk.doc` imports review_surface inside the function, so the module object is the thing
    # to patch; patching a name on `walk` would do nothing.
    monkeypatch.setattr(rv, "manuscript_dir", lambda corpus="", dir_param="": md)
    monkeypatch.setattr(rv, "_project_name", lambda corpus, md_: "proj")
    off = walk.doc(dir_param=str(md))
    on = walk.doc(dir_param=str(md), identities=True)
    assert off["ok"] and on["ok"]
    blocks_off = [b for s in off["sections"] for b in s["blocks"]]
    blocks_on = [b for s in on["sections"] for b in s["blocks"]]
    assert all("expected" not in b for b in blocks_off), "a reader pays nothing for this"
    assert blocks_on and all(b.get("expected") for b in blocks_on
                             if b["src"].get("line_start"))
    prose = next(b for b in blocks_on if b["src"]["file"] == "N1.tex"
                 and b["src"]["line_start"] == _P1_SPAN[0])
    assert prose["expected"] == [
        _prose_token("proj", "N1.tex", prose["src"]["line_start"],
                     prose["src"]["line_end"], prose["tex"])]
    # ... and the span that token addresses really is the file's bytes at those lines
    lines = (md / "N1.tex").read_text(encoding="utf-8").split("\n")
    assert prose["tex"] == "\n".join(
        lines[prose["src"]["line_start"] - 1:prose["src"]["line_end"]])
    assert _comment(md, line_start=prose["src"]["line_start"],
                    line_end=prose["src"]["line_end"],
                    expected=prose["expected"])["ok"] is True


# --------------------------------------------------------------------------- #
# 4. The rewrite door: a token must not become a licence to overwrite
# --------------------------------------------------------------------------- #
def _rewrite(md, **extra):
    payload = {"verb": "rewrite", "by": "author", "corpus": "proj", "section": "N1",
               "file": "N1.tex", "line_start": _P1_SPAN[0], "line_end": _P1_SPAN[1],
               "before": _P1_TEXT, "after": _P1_TEXT.replace("quick", "swift"),
               "passage_before": "quick", "passage_after": "swift"}
    payload.update(extra)
    return _owned_adjudicate(md, "proj", payload)


def test_the_rewrite_door_takes_a_token_and_splices(tmp_path):
    md = _md(tmp_path)
    res = _rewrite(md, expected=[_prose_token("proj", "N1.tex", *_P1_SPAN, _P1_TEXT)])
    assert res["ok"] is True and res.get("pending") is not True
    assert "swift brown fox" in (md / "N1.tex").read_text(encoding="utf-8")


def test_a_current_token_with_stale_text_re_splices_the_passage_and_never_the_span(tmp_path):
    """The state `expected` creates: the identity is current, the caller's `before` is not.

    The caller's `after` was computed against bytes that are gone, so applying it would
    overwrite an edit it never read.  The author's own passage is re-spliced instead, into the
    bytes this door reads now --- so the sentence someone else added SURVIVES the retry.
    """
    md = _md(tmp_path)
    path = md / "N1.tex"
    path.write_text(_N1.replace("lazy dog.\n", "lazy dog. Added by someone else.\n"),
                    encoding="utf-8")
    current = "\n".join(path.read_text(encoding="utf-8").split("\n")
                        [_P1_SPAN[0] - 1:_P1_SPAN[1]])
    assert current != _P1_TEXT
    res = _rewrite(md, expected=[_prose_token("proj", "N1.tex", *_P1_SPAN, current)])
    assert res["ok"] is True and res.get("pending") is not True
    after = path.read_text(encoding="utf-8")
    assert "swift brown fox" in after, "the author's own edit applied"
    assert "Added by someone else." in after, "and the other edit was not overwritten"


def test_an_unplaceable_passage_writes_nothing_and_names_the_read(tmp_path):
    md = _md(tmp_path)
    path = md / "N1.tex"
    before_bytes = path.read_bytes()
    current = "The fox. The fox."
    path.write_text(_N1.replace("The quick brown fox jumps over the lazy dog.",
                                current), encoding="utf-8")
    res = _rewrite(md, passage_before="The fox.", passage_after="The hound.",
                   expected=[_prose_token("proj", "N1.tex", *_P1_SPAN, current)])
    assert "refused" in res and res["refused"]["kind"] == "state-not-reached"
    assert res["refused"]["needed"]["read"].startswith("GET /review/fragment")
    assert path.read_text(encoding="utf-8") == _N1.replace(
        "The quick brown fox jumps over the lazy dog.", "The fox. The fox."), \
        "nothing was written"
    assert before_bytes != path.read_bytes()      # (the plant itself, not the door)
    assert _rows(md) == []


def test_a_stale_rewrite_banks_pending_and_serves_the_token_but_never_the_bytes(tmp_path):
    """The old behaviour is unchanged --- a pending row, never a guessed splice --- and the
    receipt now carries the current TOKEN, so the row is retryable.

    AND NOT THE BYTES. Serving the span here would make the mechanical retry
    (`{**request, **needed}`) arrive with a satisfied byte guard and a stale `after`, and the
    splice would overwrite whoever moved the span. The browser proof measured exactly that
    loss before this was ruled (wave1/editor-doors/proof, step `no_clobber`). The read that
    serves the span is named instead, on the home's own row."""
    md = _md(tmp_path)
    path = md / "N1.tex"
    # someone else moves the span between the caller's read and its save
    path.write_text(_N1.replace("lazy dog.", "lazy dog. Added by someone else."),
                    encoding="utf-8")
    current = "\n".join(path.read_text(encoding="utf-8").split("\n")
                        [_P1_SPAN[0] - 1:_P1_SPAN[1]])
    res = _rewrite(md)                      # `before` is the text the caller read, now stale
    assert res["pending"] is True and res["applied"] is None
    refused = res["receipt"]["refused"]
    assert refused["kind"] == "identity-stale"
    assert refused["needed"] == {"expected": [
        _prose_token("proj", "N1.tex", *_P1_SPAN, current)]}
    assert "before_content" not in refused["needed"]
    assert refused["homes"][0]["read"].startswith("source {files:[path]}")
    # ... and the mechanical retry from that `needed` alone applies, because the door replays
    # the caller's own EDIT onto the bytes that are there now
    applied = _rewrite(md, **refused["needed"])
    assert applied["ok"] is True and applied.get("pending") is not True
    after = path.read_text(encoding="utf-8")
    assert "swift brown fox" in after and "Added by someone else." in after


def test_a_retry_whose_base_is_unrelated_writes_nothing(tmp_path):
    """The merge is not a best effort. A caller whose `before` has nothing to do with the
    current text has no edit to replay --- the one changed region covers everything --- so the
    door writes neither side and names the read."""
    md = _md(tmp_path)
    res = _rewrite(md, before="text that is not in the file",
                   expected=[_prose_token("proj", "N1.tex", *_P1_SPAN, _P1_TEXT)])
    assert res["refused"]["kind"] == "state-not-reached"
    assert (md / "N1.tex").read_text(encoding="utf-8") == _N1
    assert _rows(md) == []


def test_the_merge_composes_two_edits_and_refuses_one_region(tmp_path):
    """The merge itself, on strings, in both directions and on the conflict."""
    base = "alpha beta gamma"
    assert rv._merge_edits(base, "ALPHA beta gamma", "alpha beta GAMMA") \
        == "ALPHA beta GAMMA"
    assert rv._merge_edits(base, "alpha beta GAMMA", "ALPHA beta gamma") \
        == "ALPHA beta GAMMA"
    assert rv._merge_edits(base, base, "alpha beta GAMMA") == "alpha beta GAMMA"
    assert rv._merge_edits(base, "ALPHA beta gamma", base) == "ALPHA beta gamma"
    # two edits INSIDE one word: neither can be replayed over the other
    assert rv._merge_edits(base, "alpha BETA gamma", "alpha bXta gamma") is None
    # ... while an insertion that only TOUCHES the other's boundary still composes, which is
    # the behaviour to want: "alpha beta! gamma" inserts at 10 and "ALPHA" ends at 5
    assert rv._merge_edits(base, "alpha BETA gamma", "alpha beta! gamma") \
        == "alpha BETA! gamma"


# --------------------------------------------------------------------------- #
# 5. The ruling is readable: by the board, and by a session
# --------------------------------------------------------------------------- #
def test_the_findings_read_publishes_the_ruling_so_a_refresh_shows_it(tmp_path):
    md = _md(tmp_path)
    _comment(md, disposition="keep", comment="keep this exactly as it is")
    rows = rv._feedback_findings(md, "proj")
    assert [(r["disposition"], r["altitude"]) for r in rows] == [("keep", "paragraph")]


def test_a_session_is_told_the_ruling_through_the_notes_declared_read(tmp_path):
    """`author_history {view: corrections}` is the `note` home's own declared read
    (`grammar.HOME_KINDS["note"].read`), and `_with_feedback` is what projects the ledger into
    it.  A ruling a session cannot see is a ruling the author wrote for nobody."""
    from laplace.pipeline import authoring as pa

    md = _md(tmp_path)
    _comment(md, disposition="cut", comment="cut this paragraph")
    state = pa._with_feedback({"corrections": []}, md / "feedback" / "feedback.jsonl")
    row = state["corrections"][-1]
    assert (row["disposition"], row["altitude"]) == ("cut", "paragraph")
    prompt = pa._prompt({"framing": {"purpose": "", "audience": "", "question": ""},
                         "argument": ""}, [], [], state["corrections"], [], [],
                        include_orientation=False)
    assert "RULING: cut this paragraph" in prompt


def test_the_ruling_vocabulary_is_closed_and_refuses_rather_than_banks(tmp_path):
    md = _md(tmp_path)
    for bad in ({"disposition": "delete"}, {"altitude": "sentence"}):
        res = _comment(md, **bad)
        assert "error" in res and "must be one of" in res["error"], bad
    assert _rows(md) == []
    assert rv.DISPOSITIONS == ("keep", "cut", "rework")


def test_an_absent_ruling_banks_exactly_the_row_every_caller_already_gets(tmp_path):
    """Backward compatibility, as a measurement rather than a claim: the row a caller that
    knows nothing about this packet banks has no new key anywhere in it."""
    md = _md(tmp_path)
    res = _owned_adjudicate(md, "proj", {"verb": "comment", "by": "author", "section": "N1",
                                     "coarse": True, "comment": "the section drifts"})
    assert res["ok"] is True
    row = _rows(md)[-1]
    assert set(row["anchor"]) == {"section", "paragraph_id", "quote", "coarse", "grade"}


# --------------------------------------------------------------------------- #
# 6. The block door's refusal, which used to hold its cure in a local variable
# --------------------------------------------------------------------------- #
def test_the_block_undo_refusal_serves_the_token_and_the_bytes(tmp_path, monkeypatch):
    from laplace.manuscript import blocks as mb

    md = _md(tmp_path)
    monkeypatch.setattr(mb, "_path", lambda root, project, file: (
        {}, md, md / file))
    (tmp_path / "contract").mkdir(exist_ok=True)
    edit = {"file": "N1.tex", "before": "x", "after": "text the file does not hold"}
    with pytest.raises(identity_doors.IdentityRefused) as caught:
        mb._change(tmp_path, "proj", {"operation": "undo", "edits": [edit]})
    refused = caught.value.refused
    assert str(caught.value) == "object changed since this operation; undo is refused", \
        "the owner's own sentence is unchanged, so replay sees the same refusal"
    assert refused["kind"] == "identity-stale"
    assert refused["needed"]["before_content"] == _N1
    assert refused["needed"]["expected"] == [
        str(g.mint("source-file", "proj::N1.tex", g.digest_bytes(_N1.encode("utf-8"))))]


# --------------------------------------------------------------------------- #
# 7. The census this packet must not move
# --------------------------------------------------------------------------- #
def test_no_editor_door_declares_a_guard_name_of_its_own():
    """Six doors were gated and the twenty-name census did not grow: each of them takes
    `expected` and the two that already compared a value name the value they already
    compared.  `identity_names.GUARD_KEY` is revision|digest|sha256|currentness."""
    import re

    guard = re.compile(r"revision|digest|sha256|currentness")
    editor = ["comment@paragraph", "comment@section", "comment@chapter",
              "block_change undo", "apply_proposal", "proposal_decision"]
    for key in editor:
        for name in identity_doors.DOORS[key].guard_to_home:
            assert not guard.search(name), (key, name)
    assert identity_doors.DOORS["block_change undo"].guard_to_home == {"after": "source-file"}
    for key in editor:
        if not identity_doors.DOORS[key].guard_to_home:
            assert key in identity_doors.NO_OLD_NAME


def test_every_editor_door_carries_a_date_and_the_parity_run_that_deletes_it():
    assert "2026-11-15" in identity_doors.EDITOR_EXPIRY
    assert "parity" in identity_doors.EDITOR_EXPIRY
    for key in ("comment@paragraph", "block_change undo", "apply_proposal",
                "proposal_decision"):
        assert identity_doors.DOORS[key].expiry == identity_doors.EDITOR_EXPIRY, key


def test_the_declared_altitudes_carry_their_measurement():
    for altitude in ("paragraph", "section", "chapter"):
        because = g.ADDED_PAIRS[("create", "note@" + altitude)]
        assert "129 rows" in because and "note@claim" in because


def test_the_editor_doors_are_declared_with_the_field_they_take():
    from laplace.native import declarations as d
    import laplace.web.writing_declared_http                              # noqa: F401

    for name in ("review/adjudicate", "review/adjudicate-comment",
                 "authoring/section-change", "authoring/block-change", "authoring/apply",
                 "authoring/proposal-decision"):
        schema = d.HTTP_DECLARATIONS[name].payload
        assert "expected" in schema["properties"], name
        assert schema["properties"]["expected"] is identity_doors.EXPECTED_FIELD, name
        identity = [rule for rule in d.HTTP_DECLARATIONS[name].rules
                    if rule.kind == "identity" and rule.field == "expected"]
        assert identity, name
        for rule in identity:
            assert rule.home in g.HOME_KINDS and rule.door, (name, rule)
    assert json.dumps(d.help_payload  # the help renders without the act being typed anywhere
                      and True)


# --------------------------------------------------------------------------- #
# 6. The transition's own failure modes, and the two doors whose callers now send
#    (WRITING-CONSOLIDATION-W1, continuation 1 --- each of these was a real defect
#    measured by a judge against a running server, not a hypothetical)
# --------------------------------------------------------------------------- #
def test_a_body_the_grammar_cannot_read_is_422_and_banks_nothing(tmp_path, monkeypatch):
    """The MIXED body of this very transition --- the OLD discriminator `verb:"comment"` beside
    the NEW `concept` --- used to kill the connection with no HTTP response at all.

    `grammar_request` rewrites a verb outside `g.VERBS` to the route's table verb, so `comment`
    becomes `change` and `(change, note@paragraph)` is an undeclared pair: `g.Request` raises
    `ValueError` and nothing caught it.  On the base the same body banked a comment row, so an
    uncaught raise here is a regression at the door this packet consolidates.  The refusal is
    422 with the grammar's own sentence, which names the concept."""
    md = _md(tmp_path)
    monkeypatch.setattr(rv, "manuscript_dir", lambda *a, **k: md)
    body = json.dumps({
        "verb": "comment", "concept": "note@paragraph", "by": "author",
        "target": "proj::N1.tex:%d-%d" % _P1_SPAN,
        "payload": {"section": "N1", "paragraph": "N1-p1", "coarse": False,
                    "comment": "the opener hedges", "disposition": "cut"}}).encode()
    status, _ctype, out = review_http.handle("/review/adjudicate", {"dir": ["ms"]}, "POST", body)
    answer = json.loads(out)
    assert status == 422, (status, answer)
    assert "note@paragraph" in answer["error"], answer
    assert _rows(md) == [], "a body the grammar refuses banks nothing"
    # AND THE WELL-FORMED SPELLING OF THE SAME GESTURE STILL ANSWERS 200 through this route.
    # It has to name `create` itself: this route's table verb is `change` (the rewrite act), so
    # a body that carries a `note@` concept and no verb the grammar knows is rewritten to
    # `change` and refused above. That is the grammar's own law --- a concept may not add or
    # choose a verb --- and it is why the refusal is the right answer for the mixed body rather
    # than a silent repair: `(comment, note@paragraph)` is two spellings of two different acts
    # in one body, and no door may guess which one the caller meant.
    good = json.dumps({
        "verb": "create", "concept": "note@paragraph", "by": "author",
        "target": "proj::N1.tex:%d-%d" % _P1_SPAN,
        "payload": {"section": "N1", "paragraph": "N1-p1", "coarse": False,
                    "comment": "the opener hedges", "disposition": "cut"}}).encode()
    status2, _c, out2 = review_http.handle("/review/adjudicate", {"dir": ["ms"]}, "POST", good)
    assert status2 == 200 and json.loads(out2)["ok"] is True
    assert len(_rows(md)) == 1


def test_a_stale_section_altitude_ruling_is_refused_and_the_retry_banks(tmp_path):
    """The editor's OWN send at section altitude, end to end: the token comes from
    `/review/fragment`'s `identities` (the only place the canvas can read a FILE token ---
    `walk.doc` publishes the `prose` span token and nothing else), a stale one is refused with
    `needed`, and `{**request, **needed}` banks.

    This is the altitude the editor could not gate until `commentPayload` read the fragment:
    a section ruling sent no token at all, so it banked against bytes the author may never have
    read, which is exactly what the gate exists to prevent."""
    md = _md(tmp_path)
    published = rv.fragment_view(md, "N1", "N1-p1", "proj")["identities"]
    assert "section:proj::N1.tex" in published, published
    stale = str(g.mint("section", "proj::N1.tex", g.digest_bytes(b"the file as it was")))
    refused = _comment(md, altitude="section", expected=[stale])
    assert refused["refused"]["kind"] == "identity-stale"
    assert _rows(md) == []
    needed = refused["refused"]["needed"]
    assert needed["expected"] == [published["section:proj::N1.tex"]], \
        "the token the refusal serves IS the token the read published: one producer"
    applied = _comment(md, altitude="section", **needed)
    assert applied["ok"] is True
    row = _rows(md)[-1]
    assert row["kind"] == "comment" and row["anchor"]["altitude"] == "section"


def test_a_superseded_proposal_is_refused_at_apply_and_the_cure_is_the_fresh_token(
        tmp_path, monkeypatch):
    """The race `/authoring/apply` applied blind: read version N, click after the session has
    superseded it, apply N+1 and nothing says so.

    The token is read from `pending_proposals` --- the `proposal` home's own declared read, and
    the one the editor's panel captures when it renders the card --- the session then proposes
    again, and the stale token is refused with the fresh one in `needed`.  The second call is
    what a re-read gives the next click, and it applies the revision that is NOW proposed."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_writing_proposal_recovery import prepare       # the real project/turn/proposal
    from laplace.web import authoring as ctl
    from laplace.writing.records import _fold as records_fold
    from laplace.writing import session_reads
    from laplace.native import tools as writing_tools

    records_fold._CACHE.clear()
    source, _session, turn_id, _proposed = prepare(tmp_path)
    read = session_reads.pending_proposals(tmp_path, "recovery", summary=True)["proposals"][0]
    assert read["id"] == turn_id
    token = list(read["identities"].values())
    assert len(token) == 1 and g.parse(token[0]).kind == "proposal"

    # the session supersedes what the reviewer read
    records_fold._CACHE.clear()
    assert writing_tools.execute(tmp_path, "recovery", "work", "propose_revision", {
        "answer": "A second revision.", "edits": [{
            "file": "Book.tex", "line_start": 3, "line_end": 3, "before": "Original prose.",
            "after": "Superseding prose.", "reason": "Revised again."}]}, turn_id)["ok"] is True
    records_fold._CACHE.clear()

    # THROUGH THE HTTP DOOR, because the status is half the cure: a caller that retries needs
    # to know this is "the world moved" (409) and not "your body is wrong".
    monkeypatch.setattr(ctl, "_root", lambda: tmp_path)
    status, _ctype, out = ctl.handle("/authoring/apply", {}, "POST", json.dumps(
        {"project": "recovery", "turn_id": turn_id, "expected": token}).encode())
    answer = json.loads(out)
    assert status == 409, (status, answer)
    needed = answer["refused"]["needed"]
    assert needed["expected"] and needed["expected"] != token, \
        "the refusal serves the token of the proposal that is now there"
    assert "Original prose." in source.read_text(encoding="utf-8"), "nothing was applied"
    # the cure: a re-read publishes exactly that token, which is what the next click sends
    records_fold._CACHE.clear()
    fresh = list(session_reads.pending_proposals(
        tmp_path, "recovery", summary=True)["proposals"][0]["identities"].values())
    assert fresh == needed["expected"]
    records_fold._CACHE.clear()
    ok_status, _c, applied_out = ctl.handle("/authoring/apply", {}, "POST", json.dumps(
        {"project": "recovery", "turn_id": turn_id, "expected": fresh}).encode())
    assert ok_status == 200 and json.loads(applied_out)["complete"], applied_out
    assert "Superseding prose." in source.read_text(encoding="utf-8")


def test_unqualified_apply_refuses_before_source_effect_even_after_second_candidate(tmp_path):
    """A later candidate does not make turn-only application authoritative.

    The current owner requires an exact selected version or expected identity
    before source work. This is distinct from the rewrite door's byte guard.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_writing_proposal_recovery import prepare
    from laplace.writing.records import _fold as records_fold
    from laplace.manuscript import source_application
    from laplace.native import tools as writing_tools

    records_fold._CACHE.clear()
    source, _session, turn_id, _proposed = prepare(tmp_path)
    records_fold._CACHE.clear()
    writing_tools.execute(tmp_path, "recovery", "work", "propose_revision", {
        "answer": "A second revision.", "edits": [{
            "file": "Book.tex", "line_start": 3, "line_end": 3, "before": "Original prose.",
            "after": "Superseding prose.", "reason": "Revised again."}]}, turn_id)
    records_fold._CACHE.clear()
    before = source.read_bytes()
    with pytest.raises(ValueError, match="exact proposal_version"):
        source_application.apply_proposal(tmp_path, {"project": "recovery", "turn_id": turn_id})
    assert source.read_bytes() == before



def test_the_canvas_publishes_the_file_token_the_section_ruling_is_gated_on(
        tmp_path, monkeypatch):
    """The read the page is BUILT from publishes the container token for the two altitudes whose
    container is the file, so the editor sends the identity of the bytes it is SHOWING.

    This is what makes a section ruling refusable at all: a token read beside the gate (the first
    shape of this, a `/review/fragment` read inside `commentPayload`) is current by construction
    and can never refuse, so the race between what the author read and what is there now would
    have been invisible.  Here the file moves AFTER the read, and the ruling is refused."""
    md = _md(tmp_path)
    monkeypatch.setattr(walk, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(rv, "manuscript_dir", lambda corpus="", dir_param="": md)
    monkeypatch.setattr(rv, "_project_name", lambda corpus, md_: "proj")
    off = walk.doc(dir_param=str(md))
    on = walk.doc(dir_param=str(md), identities=True)
    assert "identities" not in off, "a reader pays nothing for this either"
    published = on["identities"]
    assert published["section:proj::N1.tex"] and published["chapter:proj::N1.tex"]
    # the same value the door's own read publishes for that file: one producer, two reads
    assert published["section:proj::N1.tex"] == \
        rv.fragment_view(md, "N1", "N1-p1", "proj")["identities"]["section:proj::N1.tex"]
    read_token = published["section:proj::N1.tex"]
    # ... and it is accepted at section altitude as read
    assert _comment(md, altitude="section", expected=[read_token])["ok"] is True
    # ANOTHER WRITER MOVES THE FILE after the page was built. The token the page holds is the
    # one it read, so the next section ruling is refused with the current one in `needed`.
    (md / "N1.tex").write_text(
        (md / "N1.tex").read_text(encoding="utf-8") + "\n% N1-p3\nA third paragraph.\n",
        encoding="utf-8")
    refused = _comment(md, altitude="section", expected=[read_token])
    assert refused["refused"]["kind"] == "identity-stale"
    assert refused["refused"]["needed"]["expected"] == [
        walk.doc(dir_param=str(md), identities=True)["identities"]["section:proj::N1.tex"]], \
        "the cure is the token a fresh read of the page would publish"
    assert _comment(md, altitude="section",
                    **refused["refused"]["needed"])["ok"] is True


def _shared_history_probe(source, change, *, undo=True):
    """Execute the actual shared JS locator; the Python test owns no second algorithm."""
    import subprocess
    module=(Path(__file__).resolve().parents[1]/'src/laplace/web/static_shared/manuscript-editing.mjs').as_uri()
    program = ('import {historySpan,captureSourceChange} from '+json.dumps(module)+';'
               'let input="";for await (const chunk of process.stdin)input+=chunk;'
               'const v=JSON.parse(input),change=v.capture?captureSourceChange(v.source,v.change):v.change;'
               'console.log(JSON.stringify({change,span:historySpan(v.source,change,v.undo)}));')
    result=subprocess.run(['node','--input-type=module','-e',program],
        input=json.dumps({'source':source,'change':change,'undo':undo,'capture':'prefix' not in change}),
        text=True,capture_output=True,check=True)
    return json.loads(result.stdout)


def test_recorded_blank_structural_delete_undo_redo_uses_actual_nonempty_byte_guard(tmp_path):
    md=_md(tmp_path);path=md/'N1.tex';original=path.read_text()
    deleted=_rewrite(md,after='')
    assert deleted['ok'] and deleted.get('pending') is not True
    blank=path.read_text()
    observed=_shared_history_probe(blank,{'file':'N1.tex','line_start':5,'before':_P1_TEXT,'after':''})
    span=observed['span'];assert span['before'].strip() and len(span['before'])<100
    undone=_rewrite(md,**{key:span[key] for key in ('line_start','line_end','before','after')})
    assert undone['ok'] and undone.get('pending') is not True
    assert path.read_text()==original
    redo=_shared_history_probe(path.read_text(),observed['change'],undo=False)['span']
    redone=_rewrite(md,**{key:redo[key] for key in ('line_start','line_end','before','after')})
    assert redone['ok'] and redone.get('pending') is not True
    assert path.read_text()==blank


def test_empty_paragraph_marker_save_and_guarded_undo_preserve_inline_source_islands(tmp_path):
    md=_md(tmp_path);path=md/'N1.tex';before='Paragraph with \\ref{one} and \\ref{two}.'
    original=path.read_text().replace(_P1_TEXT,before);path.write_text(original)
    saved=_rewrite(md,before=before,after='\\par')
    assert saved['ok'] and saved.get('pending') is not True
    observed=_shared_history_probe(path.read_text(),{'file':'N1.tex','line_start':5,'before':before,'after':'\\par'})
    span=observed['span'];assert span['before']=='\\par'
    undone=_rewrite(md,**{key:span[key] for key in ('line_start','line_end','before','after')})
    assert undone['ok'] and undone.get('pending') is not True
    assert path.read_text()==original


def test_blank_inverse_guard_refuses_external_drift_after_locator_read_without_overwrite(tmp_path):
    md=_md(tmp_path);path=md/'N1.tex';assert _rewrite(md,after='')['ok']
    observed=_shared_history_probe(path.read_text(),{'file':'N1.tex','line_start':5,'before':_P1_TEXT,'after':''})
    span=observed['span'];before=path.read_text().replace('% N1-p1','% CHANGED-N1-p1');path.write_text(before)
    refused=_rewrite(md,**{key:span[key] for key in ('line_start','line_end','before','after')})
    assert refused.get('pending') is True or not refused.get('ok')
    assert path.read_text()==before


def test_real_shaped_long_tex_neighbor_blank_delete_inverse_preserves_current_pass_through(tmp_path):
    md=_md(tmp_path);path=md/'N1.tex';left='Earlier paragraph with \\ref{one}. '+('Unchanged words. '*40)
    right='Later paragraph with \\ref{two}. '+('More unchanged words. '*40)
    original='\\section{Introduction}\n'+left+'\n'+_P1_TEXT+'\n'+right+'\n'
    path.write_text(original)
    assert _rewrite(md,line_start=3,line_end=3,after='')['ok']
    blank=path.read_text();observed=_shared_history_probe(blank,{'file':'N1.tex','line_start':3,'before':_P1_TEXT,'after':''})
    # This change is outside the saved160-character prefix and is never called historical.
    edited=blank.replace('Earlier paragraph', 'Externally improved earlier paragraph');path.write_text(edited)
    span=_shared_history_probe(edited,observed['change'])['span']
    assert span['before'].strip() and 500<len(span['before'])<len(edited)
    restored=_rewrite(md,**{key:span[key] for key in ('line_start','line_end','before','after')})
    assert restored['ok'] and restored.get('pending') is not True
    assert path.read_text()==original.replace('Earlier paragraph','Externally improved earlier paragraph')
    # The fresh whole-neighbor byte guard also refuses a race beyond the historical fragment.
    assert _rewrite(md,line_start=3,line_end=3,after='')['ok']
    inverse=_shared_history_probe(path.read_text(),observed['change'])['span']
    changed=path.read_text().replace('Externally improved earlier paragraph','Changed after locator');path.write_text(changed)
    refusal=_rewrite(md,**{key:inverse[key] for key in ('line_start','line_end','before','after')})
    assert refusal.get('pending') is True or not refusal.get('ok')
    assert path.read_text()==changed


def test_structural_delete_inverted_preflight_hunk_guards_context_at_actual_owner(tmp_path):
    md=_md(tmp_path);path=md/'N1.tex';original=path.read_text()
    planned=original.replace(_P1_TEXT,'')
    inverse=_shared_history_probe(planned,{'file':'N1.tex','line_start':5,'before':_P1_TEXT,'after':''})['span']
    request={'line_start':inverse['line_start'],
        'line_end':inverse['line_start']+len(inverse['after'].split('\n'))-1,
        'before':inverse['after'],'after':inverse['before']}
    assert request['after'].strip()
    applied=_rewrite(md,**request)
    assert applied['ok'] and applied.get('pending') is not True
    assert path.read_text()==planned
    # Undo uses this same complete guarded hunk; no blank before reaches admission.
    restored=_rewrite(md,line_start=inverse['line_start'],line_end=inverse['line_end'],
        before=inverse['before'],after=inverse['after'])
    assert restored['ok'] and restored.get('pending') is not True
    assert path.read_text()==original
    path.write_text(original.replace('% N1-p1','% Changed-p1'))
    changed=path.read_bytes();refused=_rewrite(md,**request)
    assert refused.get('pending') is True or not refused.get('ok')
    assert path.read_bytes()==changed


def _served_rewrite(md, **extra):
    first=_rewrite(md,expected=[_prose_token('proj','N1.tex',5,5,'old projection')],**extra)
    assert first['pending'] is True
    return first,{'expected':first['receipt']['refused']['needed']['expected'],
                  'rewrite_retry':first['receipt']['rewrite_retry'],**extra}


def test_served_retry_resolves_only_exact_pending_intent_after_successful_source_swap(tmp_path):
    md=_md(tmp_path);first,again=_served_rewrite(md,note='  Retain the rationale.  ',source='editor-undo')
    result=_rewrite(md,**again)
    assert result['ok'] and result['pending'] is False and result['applied']
    settlement=result['receipt']['retry_settlement'];assert settlement['status']=='RESOLVED'
    assert settlement['pending_id']==first['record']['id']
    rows={row['id']:row for row in _rows(md)};pending=rows[first['record']['id']]
    assert pending['status']=='resolved'
    assert pending['status_history'][-1]['applied_record_id']==result['record']['id']
    assert rows[result['record']['id']]['anchor']['rewrite_retry']==again['rewrite_retry']
    before=(md/'N1.tex').read_bytes();count=len(rows)
    repeated=_rewrite(md,**again)
    assert repeated['reason']=='rewrite-retry-refused'
    assert (md/'N1.tex').read_bytes()==before and len(_rows(md))==count


def test_concurrent_same_retry_has_one_source_effect_and_fresh_second_refusal(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    md = _md(tmp_path)
    first, again = _served_rewrite(md)
    entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
    original = rv._rewrite_retry_check
    observations = []
    from contextlib import contextmanager
    from laplace.manuscript import manuscript_source
    original_lease = manuscript_source.source_mutation
    second_thread = []
    @contextmanager
    def lease(paths, **kwargs):
        if second_thread and threading.get_ident() == second_thread[0]:
            second_started.set()
        with original_lease(paths, **kwargs) as held:
            yield held
    monkeypatch.setattr(manuscript_source, 'source_mutation', lease)
    def checked(records, *args):
        result = original(records, *args)
        observations.append(next(r['status'] for r in records if r['id'] == first['record']['id']))
        if len(observations) == 1:
            entered.set()
            assert release.wait(2)
        return result
    monkeypatch.setattr(rv, '_rewrite_retry_check', checked)
    def second():
        second_thread.append(threading.get_ident())
        return _rewrite(md, **again)
    with ThreadPoolExecutor(2) as pool:
        one = pool.submit(_rewrite, md, **again)
        assert entered.wait(1)
        two = pool.submit(second)
        assert second_started.wait(1)
        assert not two.done() and observations == ['open']
        release.set()
        applied, refused = one.result(timeout=2), two.result(timeout=2)
    assert applied['applied'] and applied['receipt']['retry_settlement']['status'] == 'RESOLVED'
    assert refused['reason'] == 'rewrite-retry-refused'
    assert observations == ['open', 'resolved']
    assert len([r for r in _rows(md) if r['kind'] == 'author-rewrite']) == 1


def test_ordinary_writers_share_fresh_file_read_and_do_not_lose_disjoint_edits(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    md = _md(tmp_path)
    entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
    original = rv.identity_doors.gate
    paused = False
    from contextlib import contextmanager
    from laplace.manuscript import manuscript_source
    original_lease = manuscript_source.source_mutation
    second_thread = []
    @contextmanager
    def lease(paths, **kwargs):
        if second_thread and threading.get_ident() == second_thread[0]:
            second_started.set()
        with original_lease(paths, **kwargs) as held:
            yield held
    monkeypatch.setattr(manuscript_source, 'source_mutation', lease)
    def gate(*args, **kwargs):
        nonlocal paused
        result = original(*args, **kwargs)
        if args[0] == 'apply_revision' and not paused:
            paused = True
            entered.set()
            assert release.wait(2)
        return result
    monkeypatch.setattr(rv.identity_doors, 'gate', gate)
    before = 'The lazy dog sleeps here in the afternoon sun.'
    def second():
        second_thread.append(threading.get_ident())
        return _rewrite(md, line_start=8, line_end=8, before=before,
                        after=before.replace('lazy', 'sleepy'), passage_before='lazy', passage_after='sleepy')
    with ThreadPoolExecutor(2) as pool:
        one = pool.submit(_rewrite, md)
        assert entered.wait(1)
        two = pool.submit(second)
        assert second_started.wait(1) and not two.done()
        release.set()
        assert one.result(timeout=2)['applied'] and two.result(timeout=2)['applied']
    assert 'swift brown fox' in (md/'N1.tex').read_text()
    assert 'The sleepy dog sleeps' in (md/'N1.tex').read_text()


def test_retry_rechecks_source_after_other_cooperating_writer(tmp_path):
    md = _md(tmp_path)
    first, again = _served_rewrite(md)
    edited = _owned_adjudicate(md, 'proj', {'verb':'edit-in-place', 'by':'other',
        'section':'N1', 'file':'N1.tex', 'before':'quick', 'after':'nimble'})
    assert edited['applied']
    before = (md/'N1.tex').read_bytes()
    result = _rewrite(md, **again)
    assert result.get('pending') or not result.get('ok')
    assert (md/'N1.tex').read_bytes() == before
    assert next(r for r in _rows(md) if r['id'] == first['record']['id'])['status'] == 'open'


@pytest.mark.parametrize('change',[{'after':'Different effect.'},{'before':_P1_TEXT+' '},
    {'note':'Different rationale.'},{'reason':'Different reason.'},{'scope':'voice'},
    {'source':'different-origin'},{'by':'another-actor'},{'file':'main.tex'},
    {'line_start':4,'line_end':4},{'passage_after':'Different intent.'}])
def test_retry_lineage_changed_original_intent_or_scope_refuses_before_effect(tmp_path,change):
    md=_md(tmp_path);first,again=_served_rewrite(md)
    before=(md/'N1.tex').read_bytes();count=len(_rows(md))
    result=_rewrite(md,**{**again,**change})
    assert result['reason']=='rewrite-retry-refused'
    assert (md/'N1.tex').read_bytes()==before and len(_rows(md))==count
    assert next(row for row in _rows(md) if row['id']==first['record']['id'])['status']=='open'


def test_failed_retry_or_source_swap_does_not_retire_first_pending(tmp_path,monkeypatch):
    md=_md(tmp_path/'retry');first,again=_served_rewrite(md)
    result=_rewrite(md,**{**again,'expected':[_prose_token('proj','N1.tex',5,5,'still stale')]})
    assert result['pending'] is True
    assert next(row for row in _rows(md) if row['id']==first['record']['id'])['status']=='open'
    assert _P1_TEXT in (md/'N1.tex').read_text()
    md=_md(tmp_path/'swap');first,again=_served_rewrite(md)
    from laplace.manuscript import manuscript_bridge
    def cannot_resolve(*args,**kwargs):pytest.fail('resolution happened before successful swap')
    monkeypatch.setattr(manuscript_bridge,'feedback_resolve',cannot_resolve)
    replace=Path.replace
    def failed_swap(path,target):
        if path.name.endswith('.rewriteswap'):raise OSError('controlled failed swap')
        return replace(path,target)
    monkeypatch.setattr(Path,'replace',failed_swap)
    before=(md/'N1.tex').read_bytes();result=_rewrite(md,**again)
    assert result['reason']=='swap-failed' and result['applied'] is None
    assert (md/'N1.tex').read_bytes()==before
    assert next(row for row in _rows(md) if row['id']==first['record']['id'])['status']=='open'


def test_retry_resolution_failure_preserves_applied_ack_and_refuses_effect_replay(tmp_path,monkeypatch):
    md=_md(tmp_path);first,again=_served_rewrite(md)
    from laplace.manuscript import manuscript_bridge
    monkeypatch.setattr(manuscript_bridge,'feedback_resolve',lambda *a,**k:(_ for _ in ()).throw(OSError('controlled status failure')))
    result=_rewrite(md,**again)
    assert result['ok'] and result['applied'] and result['pending'] is False
    assert 'swift' in (md/'N1.tex').read_text()
    assert result['receipt']['retry_settlement']['status']=='UNRESOLVED'
    assert first['record']['id'] in result['receipt']['retry_warning']
    assert result['receipt']['retry_warning'] in result['receipt']['words']
    count=len(_rows(md));before=(md/'N1.tex').read_bytes()
    repeat=_rewrite(md,**again)
    assert repeat['reason']=='rewrite-retry-refused'
    assert (md/'N1.tex').read_bytes()==before and len(_rows(md))==count


def test_retry_status_race_does_not_overwrite_explicit_dismissal(tmp_path,monkeypatch):
    md=_md(tmp_path);first,again=_served_rewrite(md)
    from laplace.manuscript import manuscript_bridge
    resolve=manuscript_bridge.feedback_resolve
    def changed(*args,**kwargs):
        resolve(*args[:3],status='dismissed',ledger=kwargs['ledger'],by='author',note='Explicit separate decision')
        return resolve(*args,**kwargs)
    monkeypatch.setattr(manuscript_bridge,'feedback_resolve',changed)
    result=_rewrite(md,**again)
    assert result['applied'] and result['receipt']['retry_settlement']['status']=='UNRESOLVED'
    assert next(row for row in _rows(md) if row['id']==first['record']['id'])['status']=='dismissed'


def test_retry_witness_is_shared_by_declared_http_and_native_grammar_and_old_rows_do_not_migrate(tmp_path):
    from jsonschema import validate
    from laplace.web import writing_declared_http
    from laplace.native import declarations as writing_declarations
    md=_md(tmp_path);first,again=_served_rewrite(md);witness=again['rewrite_retry']
    validate(witness,writing_declarations.HTTP_DECLARATIONS['review/adjudicate'].payload['properties']['rewrite_retry'])
    request=wv.grammar_request({'verb':'change','concept':'prose@paragraph','target':'proj::N1.tex:5-5','by':'author',
        'expected':again['expected'],'payload':{'before_content':_P1_TEXT,'after':_P1_TEXT.replace('quick','swift'),'section':'N1','passage_before':'quick','passage_after':'swift','rewrite_retry':witness}},name='review/adjudicate')
    native=review_http._owner_adjudication(request,{'corpus':'proj'})
    assert native['rewrite_retry']==witness
    result=_owned_adjudicate(md,'proj',native)
    assert result['applied'] and result['receipt']['retry_settlement']['status']=='RESOLVED'
    md=_md(tmp_path/'legacy');first,again=_served_rewrite(md);path=md/'feedback/feedback.jsonl';rows=_rows(md)
    rows[0]['anchor'].pop('rewrite_intent_sha256');path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    before=(md/'N1.tex').read_bytes();result=_rewrite(md,**again)
    assert result['reason']=='rewrite-retry-refused' and (md/'N1.tex').read_bytes()==before


@pytest.mark.parametrize('alter',[lambda x:x.update(schema_version='laplace.rewrite-retry/99'),
    lambda x:x.update(pending_id='missing'),lambda x:x.update(extra='not allowed'),
    lambda x:x.update(intent_sha256='A'*64)])
def test_malformed_or_missing_retry_witness_cannot_apply_or_retire(tmp_path,alter):
    md=_md(tmp_path);first,again=_served_rewrite(md)
    alter(again['rewrite_retry']);before=(md/'N1.tex').read_bytes();count=len(_rows(md))
    result=_rewrite(md,**again);assert result['reason']=='rewrite-retry-refused'
    assert (md/'N1.tex').read_bytes()==before and len(_rows(md))==count


def test_retry_source_bytes_preserve_unicode_whitespace_and_unknown_lineage_is_not_inferred(tmp_path):
    md=_md(tmp_path);path=md/'N1.tex';old=_P1_TEXT+' α  ';path.write_text(path.read_text().replace(_P1_TEXT,old))
    first=_rewrite(md,before=old,after=' Unicode β  ',expected=[_prose_token('proj','N1.tex',5,5,'old')])
    again={'before':old,'after':' Unicode β  ','expected':first['receipt']['refused']['needed']['expected'],
           'rewrite_retry':first['receipt']['rewrite_retry']}
    result=_rewrite(md,**again);assert result['applied'] and path.read_text().split('\n')[4]==' Unicode β  '
    # No carried lineage means no automatic retirement, even for identical intent.
    md=_md(tmp_path/'no-lineage');first,again=_served_rewrite(md);again.pop('rewrite_retry')
    applied=_rewrite(md,**again);assert applied['applied'] and 'retry_settlement' not in applied['receipt']
    assert next(row for row in _rows(md) if row['id']==first['record']['id'])['status']=='open'


def _tree_digest(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()}


def test_a_rewrite_outside_its_owning_root_refuses_before_any_read_staging_feedback_or_effect(tmp_path, monkeypatch):
    """RD-EDITOR-ROOT: the public boundary admits ONE owning root and proves the target lies inside it
    (symlinks resolved) before the source lease, staging, feedback or effect. A wrong explicit root, a default
    root that does not own the manuscript, and a symlink escape all refuse with nothing written anywhere; the
    strict receipt fence is never what stops a write after the fact."""
    payload = {"verb": "rewrite", "by": "author", "corpus": "proj", "section": "N1", "file": "N1.tex",
               "line_start": _P1_SPAN[0], "line_end": _P1_SPAN[1], "before": _P1_TEXT,
               "after": _P1_TEXT.replace("quick", "swift"), "passage_before": "quick", "passage_after": "swift",
               "expected": [_prose_token("proj", "N1.tex", *_P1_SPAN, _P1_TEXT)]}
    checkout = tmp_path / "checkout"; md = _md(checkout)
    elsewhere = tmp_path / "elsewhere"; elsewhere.mkdir()
    outside = tmp_path / "outside"; outside.mkdir(); (outside / "real.tex").write_text(_N1, encoding="utf-8")
    before = _tree_digest(tmp_path)
    # a wrong explicit root
    refused = rv.adjudicate(md, "proj", dict(payload), repo_root=elsewhere)
    assert refused["reason"] == "source-outside-owning-root" and refused["refused_before_effect"] is True
    # the ambient default root does not own this manuscript
    monkeypatch.setattr(rv, "_repo_root", lambda: elsewhere)
    assert rv.adjudicate(md, "proj", dict(payload))["reason"] == "source-outside-owning-root"
    assert _tree_digest(tmp_path) == before and not _rows(md)
    # a symlink inside the manuscript that resolves outside the owning root
    (md / "N1.tex").unlink(); (md / "N1.tex").symlink_to(outside / "real.tex")
    before = _tree_digest(tmp_path)
    # ... named by file: the manuscript fence already refuses it before any effect
    assert rv.adjudicate(md, "proj", dict(payload), repo_root=checkout)["reason"] == "no-fragment"
    # ... resolved by section stem: the owning-root fence refuses it before any effect
    by_section = {key: value for key, value in payload.items() if key != "file"}
    assert rv.adjudicate(md, "proj", by_section, repo_root=checkout)["reason"] == "source-outside-owning-root"
    assert _tree_digest(tmp_path) == before and not _rows(md)
    assert "swift" not in (outside / "real.tex").read_text(encoding="utf-8")
    # the same request under its true owning root applies once with an exact in-root receipt
    (md / "N1.tex").unlink(); (md / "N1.tex").write_text(_N1, encoding="utf-8")
    applied = rv.adjudicate(md, "proj", dict(payload), repo_root=checkout)
    assert applied["ok"] is True and applied.get("pending") is not True
    files = applied["source_effect"]["files"] if "files" in applied["source_effect"] else applied["owned_changes"]["files"]
    assert [row["path"] for row in files] == ["ms/N1.tex"]
    assert "swift brown fox" in (md / "N1.tex").read_text(encoding="utf-8")


def test_the_admitted_root_reaches_the_inner_rewrite_feedback_and_pending_adapters(tmp_path, monkeypatch):
    """RD-EDITOR-ROOT propagation: with the ambient root pointing somewhere else, an explicitly rooted
    applied rewrite and a stale (pending) rewrite bank their checkout-relative file under THEIR admitted root,
    and nothing is written outside the fixture."""
    checkout = tmp_path / "checkout"; md = _md(checkout)
    elsewhere = tmp_path / "elsewhere"; elsewhere.mkdir()
    monkeypatch.setattr(rv, "_repo_root", lambda: elsewhere)
    applied = rv.adjudicate(md, "proj", {"verb": "rewrite", "by": "author", "corpus": "proj", "section": "N1",
        "file": "N1.tex", "line_start": _P1_SPAN[0], "line_end": _P1_SPAN[1], "before": _P1_TEXT,
        "after": _P1_TEXT.replace("quick", "swift"), "passage_before": "quick", "passage_after": "swift",
        "expected": [_prose_token("proj", "N1.tex", *_P1_SPAN, _P1_TEXT)]}, repo_root=checkout)
    assert applied["ok"] is True and applied.get("pending") is not True
    stale = rv.adjudicate(md, "proj", {"verb": "rewrite", "by": "author", "corpus": "proj", "section": "N1",
        "file": "N1.tex", "line_start": _P1_SPAN[0], "line_end": _P1_SPAN[1], "before": _P1_TEXT,
        "after": _P1_TEXT.replace("quick", "slow")}, repo_root=checkout)
    assert stale.get("pending") is True
    rows = _rows(md)
    assert [row["anchor"].get("repo_file") for row in rows[-2:]] == ["ms/N1.tex", "ms/N1.tex"]
    assert not any(elsewhere.rglob("*"))


def test_proposal_decision_offers_exactly_the_canonical_token_field_its_entry_admits(tmp_path, monkeypatch):
    """RD-EDITOR-DECLARATION: the offered schema (HTTP declaration and the native owner input schema, one
    decision_contract) and the no-hydration entry agree on the canonical `expected` field: malformed items are
    refused by both, well-formed owner tokens pass the shape, and the decision-specific guards remain."""
    from jsonschema import Draft202012Validator
    from laplace.manuscript import manuscript_proposals
    from laplace.native import declarations as wd
    from laplace.writing import session_reads
    from laplace.writing import records as writing_records
    import laplace.web.writing_declared_http                                   # noqa: F401  (registers HTTP declarations)
    offered = {"http": wd.HTTP_DECLARATIONS["authoring/proposal-decision"].payload,
               "native": wd.owner_input_schema("authoring/proposal-decision")}
    base = {"project": "proj", "decision": "accept", "turn_id": "WT-x", "edit_id": "E1", "proposal_version": "v1"}
    token = _prose_token("proj", "N1.tex", *_P1_SPAN, _P1_TEXT)
    for name, schema in offered.items():
        assert schema["properties"]["expected"] == identity_doors.EXPECTED_FIELD, name
        check = Draft202012Validator(schema)
        body = dict(base) if name == "http" else {k: v for k, v in base.items() if k != "project"}
        assert not list(check.iter_errors({**body, "expected": [token]})), name
        for bad in ([1], [""], [{"token": token}], "not-an-array"):
            assert list(check.iter_errors({**body, "expected": bad})), (name, bad)
        # decision-specific guards are untouched: a decision needs its candidate address
        assert list(check.iter_errors({k: v for k, v in body.items() if k not in {"turn_id", "edit_id"}}))
    # the real entry refuses the same malformed items before any hydration, lock or effect
    monkeypatch.setattr(session_reads, '_records', lambda *a, **k: pytest.fail("hydrated before admission"))
    monkeypatch.setattr(writing_records, 'proposal_write_lock', lambda *a, **k: pytest.fail("locked before admission"))
    for bad in ([1], [""], [{"token": token}]):
        with pytest.raises(identity_doors.IdentityRefused):
            manuscript_proposals.decide(tmp_path, "proj", {**base, "expected": bad})
