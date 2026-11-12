"""The /review HTTP door (adapter): parses review routes and calls the review owner (laplace.manuscript.review_surface).

Moved out of review_surface on 2026-10-21 so the domain module serves no route and reads no served cockpit state;
the scanner dispatches /review* here.
"""
from __future__ import annotations

import json

from laplace.manuscript import review_surface as owner
from laplace.native import verbs as writing_verbs


# ---- moved from laplace.manuscript.review_surface (2026-10-21, core native/physical closure)
def _read_last_visit(key: str) -> str:
    """The author's persisted last-visit cursor for a review ``key`` (W2.4): read
    from the gitignored .cockpit.json via scanner (its one writer). Pure read and
    FAIL-CLOSED - a broken cockpit degrades to no baseline, never a raise."""
    if not key:
        return ""
    try:
        from laplace.web import scanner as _sc
        return _sc.review_last_visit(key)
    except Exception:
        return ""


#: (grammar verb, concept object) -> the old adjudication verb the executor branches on.
#: ONE row per act, and it is the shim: `identity_doors.DOORS` holds the same two acts with
#: their expiry, and nothing else in the tree spells the translation. The ALTITUDE is not in
#: this table because it is in the concept, which is where the grammar keeps it.
_OLD_ADJUDICATION = {("change", "prose"): "rewrite", ("create", "note"): "comment"}


def _owner_adjudication(request, payload: dict) -> dict:
    """One grammar request as the body the existing executor already reads.

    A shim rewrites; it never implements (GRAMMAR.md section 6 rule 1). So this restores the
    old discriminator and the owner's own key spellings and hands the result to the SAME
    `adjudicate`, which is why differential replay cannot diverge between the two spellings:
    there is one executor and one ledger append underneath both.

    The request's `target` is the home id the act is about --- `<project>::<file>:<a>-<b>` for
    the `prose` home --- so the file and the span are read off it rather than repeated in the
    payload: a caller that sent both could send two different spans and the door would have
    to pick one.
    """
    old = _OLD_ADJUDICATION.get((request.verb, request.object))
    if old is None:
        return {"error": "no editor act is declared for %s %s; the declared acts are %r"
                         % (request.verb, request.concept,
                            sorted("%s %s" % (v, o) for v, o in _OLD_ADJUDICATION))}
    body = writing_verbs.owner_body(request, verb=old)
    for key in ("corpus", "dir"):
        if payload.get(key) and not body.get(key):
            body[key] = payload[key]
    if old == "comment":
        body["altitude"] = request.altitude
    target = str(request.target or "")
    if "::" in target:
        _project, _, where = target.partition("::")
        span = where.rpartition(":")[2]
        if "-" in span and span.replace("-", "").isdigit():
            where = where[:len(where) - len(span) - 1]
            start, _, end = span.partition("-")
            body.setdefault("line_start", int(start))
            body.setdefault("line_end", int(end))
        body.setdefault("file", where)
    return body


def handle(path: str, query: dict, method: str, body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/review*`` request. Returns (status, content_type, body) or None
    when the path is not ours (the scanner falls through to its own routing)."""
    if path != "/review" and not path.startswith("/review/"):
        return None
    method = (method or "GET").upper()

    if path == "/review" and method == "GET":
        # W2 CONSOLIDATION: the review PAGE folded into /artefact's annotate mode (the scanner
        # 301-redirects the bare /review route). This module keeps its /review/* DATA producers
        # (findings/adjudicate/nodemap/compare — re-housed by the artefact panes); the PAGE is
        # gone — so it names where it went instead of serving the deleted review_surface.html.
        # NOTE a browser never reaches this JSON: the scanner owns the bare-route 301
        # (scanner.py, the W2 consolidation block in do_GET) BEFORE delegating here —
        # this branch answers only direct module calls; not a missing redirect.
        return owner._json_resp(200, {"consolidated_into": "/artefact",
                                "note": "review is the annotate mode of the artefact surface (W2)"})

    if path == "/review/context" and method == "GET":
        # the bare-route bootstrap (W0.2): which project does a bare /review open
        # on? The active project + its server-derived main tex, so the page can
        # resolve silently to the real corpus instead of a "no ?corpus=" shell.
        from laplace.research import corpus_ingest as _ci
        return owner._json_resp(200, _ci.project_context(owner._repo_root(),
                                                   owner._q1(query, "corpus")))

    if path == "/review/artefacts" and method == "GET":
        md, corpus, _ = owner._resolve(query)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir (must resolve "
                                             "inside the repo root)"})
        return owner._json_resp(200, owner.artefacts(md))

    if path == "/review/nodemap" and method == "GET":
        md, _, _ = owner._resolve(query)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        return owner._json_resp(200, owner.nodemap_state(md))

    if path == "/review/his-hand" and method == "GET":
        # the author's own edited ranges in a source file — the diff against the newest
        # machine-minted baseline (the rail attributes by kind; read-only, never writes).
        # ``?hunks=1`` serves the SAME producer unprojected: each passage keeps its
        # ``before``/``after`` line lists, which is what a band showing the rewrite
        # expandably needs. Default stays the bare ranges — no existing reader moves.
        md, corpus, _ = owner._resolve(query)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        file_rel = owner._q1(query, "file")
        if not file_rel:
            return owner._json_resp(400, {"error": "file is required (a repo-relative tex path)"})
        if owner._q1(query, "hunks") in ("1", "true", "yes"):
            return owner._json_resp(200, owner.hand_hunks(corpus, file_rel))
        return owner._json_resp(200, owner.his_hand(corpus, file_rel))

    if path == "/review/findings" and method == "GET":
        md, corpus, _ = owner._resolve(query)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        # stateless view params (scout holes 2 + 4): ?since= is the client-held
        # visit cursor; ?cls= + ?limit=/?offset= are the rail's facet + head.
        try:
            limit = int(owner._q1(query, "limit") or 0)
            offset = int(owner._q1(query, "offset") or 0)
        except ValueError:
            limit = offset = 0
        board = owner.findings(md, owner._project_name(corpus, md),
                         owner._q1(query, "dials") or None,
                         since=owner._q1(query, "since"))
        return owner._json_resp(200, owner._board_head(board, owner._q1(query, "cls"),
                                           limit, offset))

    if path == "/review/summary" and method == "GET":
        # W2.4 - the deltas-first strata summary FIRST PAINT ships (bounded ≤16KB),
        # never the finding bodies. The last-visit cursor rides .cockpit.json now
        # (W2.4 supersedes the localStorage baseline for this surface): read it here
        # so "new since your last visit" is server-computed, one bounded fetch.
        md, corpus, _ = owner._resolve(query)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        key = owner._visit_key(corpus, owner._q1(query, "dir"))
        # an explicit ?since= (a stale tab, a test) overrides the persisted cursor
        since = owner._q1(query, "since") or _read_last_visit(key)
        return owner._json_resp(200, owner.summary(md, owner._project_name(corpus, md),
                                       owner._q1(query, "dials") or None,
                                       since=since, corpus=corpus))

    if path == "/review/visit" and method == "POST":
        # bank the author's last-visit cursor for this corpus/dir into .cockpit.json,
        # NESTED-merged so every other cockpit key AND every other corpus's cursor
        # survives (W0.2 additive-merge, one level deeper). GET never writes; this is
        # the one write that moves the "new since" baseline forward, monotone.
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            payload = {}
        if not isinstance(payload, dict):
            return owner._json_resp(400, {"error": "body must be a json object"})
        corpus = (payload.get("corpus") or owner._q1(query, "corpus") or "").strip()
        dir_param = (payload.get("dir") or owner._q1(query, "dir") or "").strip()
        key = owner._visit_key(corpus, dir_param)
        ts = str(payload.get("ts") or payload.get("max_ts") or "").strip()
        if not key or not ts:
            return owner._json_resp(400, {"error": "corpus/dir and ts are required"})
        from laplace.web import scanner as _sc
        return owner._json_resp(200, _sc.record_review_visit(key, ts))

    if path == "/review/fragment" and method == "GET":
        # the READ half of edit-in-place (B13.2): the SOURCE prose the inline editor
        # edits + the unit's protection state. The WRITE is the edit-in-place verb on
        # /review/adjudicate — this route never mutates a byte.
        md, _, _ = owner._resolve(query)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        res = owner.fragment_view(md, owner._q1(query, "section"), owner._q1(query, "paragraph"),
                            owner._project_name(owner._q1(query, "corpus"), md))
        return owner._json_resp(200 if res.get("ok") else 422, res)

    if path == "/review/compile-log" and method == "GET":
        # the honest-badge seam: read the paper's full main.log and lift its problem
        # blocks, so the surface can badge a compile that exited clean over a broken
        # source (the recoverable error the 60-line recompile tail drops). Read-only.
        md, _, _ = owner._resolve(query)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        return owner._json_resp(200, owner.compile_log_view(md, owner._q1(query, "file") or ""))

    if path == "/review/rebuild" and method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            payload = {}
        corpus = payload.get("corpus") or owner._q1(query, "corpus")
        dir_param = payload.get("dir") or owner._q1(query, "dir")
        md = owner.manuscript_dir((corpus or "").strip(), (dir_param or "").strip())
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        res = owner.rebuild(md, payload.get("dials") or owner._q1(query, "dials") or None)
        return owner._json_resp(200 if res.get("ok") else 422, res)

    if path == "/review/adjudicate" and method == "POST":
        # the adjudication verbs — the ONE roster is the executor docstring
        # (``adjudicate``, above): eight verbs, edit-in-place included; do not
        # restate a count here (it drifted once already). Validate-before-persist
        # (the storyboard idiom); every write is one append through the one door.
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return owner._json_resp(400, {"error": "bad json"})
        if not isinstance(payload, dict):
            return owner._json_resp(400, {"error": "body must be a json object"})
        corpus = (payload.get("corpus") or owner._q1(query, "corpus") or "").strip()
        dir_param = (payload.get("dir") or owner._q1(query, "dir") or "").strip()
        md = owner.manuscript_dir(corpus, dir_param)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        # ── THE ONE REQUEST SHAPE (WRITING-CONSOLIDATION-W1) ───────────────────────────
        # A body that carries `concept` is a grammar request and is served through the one
        # table: the act is read off `writing_verbs.HTTP_BY_NAME`, the old adjudication verb
        # the executor branches on is restored by the shim, and the SAME `adjudicate` runs.
        # A body without `concept` is the old flat payload and nothing about it changes, so
        # the recorded corpus replays byte-identically through this line.
        #
        # A BODY THE GRAMMAR CANNOT READ IS 422, NOT A DEAD CONNECTION. `g.Request.__post_init__`
        # raises `ValueError` for a concept or a (verb, concept) pair that is not declared, and
        # the natural MIXED body of exactly this transition --- the OLD discriminator
        # `verb:"comment"` beside the NEW `concept` --- is one of those: `grammar_request`
        # rewrites a verb outside `g.VERBS` to the route's table verb (`writing_verbs.py:2063`),
        # so `comment` becomes `change` and `(change, note@paragraph)` is undeclared. Uncaught,
        # that ValueError left the request with NO HTTP response at all (measured:
        # `http.client.RemoteDisconnected`), where the base banked a comment row. The refusal
        # is the grammar's own sentence, verbatim, so the caller is told which concept it is
        # and 422 keeps the status every other bad body already gets at this door --- the same
        # 422 `_owner_adjudication`'s `{"error": …}` becomes two lines below.
        try:
            request = writing_verbs.grammar_request(payload, name="review/adjudicate")
        except ValueError as exc:
            return owner._json_resp(422, {"error": str(exc)})
        if request is not None:
            payload = _owner_adjudication(request, payload)
            if "error" in payload:
                return owner._json_resp(422, payload)
        res = owner.adjudicate(md, owner._project_name(corpus, md), payload)
        # A refusal that carries `needed` is 409, not 422: 422 says "this body is wrong" and
        # 409 says "the world moved and here is the cure", which is the difference between a
        # caller that must think and a caller that retries. Every other error keeps 422, so
        # no recorded status moves.
        if res.get("refused"):
            return owner._json_resp(409, res)
        return owner._json_resp(res.pop("status", 200 if res.get("ok") else 422), res)

    if path == "/review/provenance" and method == "GET":
        # the upward view at the point of adjudication: the node's conceptric
        # upstream + its friction-ledger minting history. Corpus-scoped (the
        # ledger is corpus-keyed); a dir-only review has no minting trace.
        node = owner._q1(query, "node")
        if not node:
            return owner._json_resp(400, {"error": "node is required for provenance"})
        return owner._json_resp(200, owner.provenance(owner._q1(query, "corpus"), node))

    if path == "/review/substrate" and method == "GET":
        md, corpus, _ = owner._resolve(query)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        return owner._json_resp(200, owner.substrate_queue(md, corpus=corpus,
                                               since=owner._q1(query, "since")))

    if path == "/review/learned" and method == "GET":
        # scout hole 1 — the "what the loop learned" rollup: consumed
        # friction/fork records by owning_layer with resolution evidence, the
        # open-fork queue head, and the open counts, over the engine ledger AND
        # every registered project's L1 ledger. Repo-scoped (no manuscript dir);
        # the Law I budget (≤40 rows / ≤16KB) is enforced inside learned().
        return owner._json_resp(200, owner.learned(since=owner._q1(query, "since")))

    if path == "/review/dismissals" and method == "GET":
        # the dismissal audit, STRATIFIED by (kind, fingerprint): the active
        # suppressions folded into per-class rows the author rules on with the
        # EXISTING calibrate (agree) / revoke (overrule) verbs. Read-only.
        md, _, _ = owner._resolve(query)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        return owner._json_resp(200, owner.dismissal_audit(md, owner._q1(query, "dials") or None))

    if path == "/review/states" and method == "GET":
        # B13.4: the banked-state enumeration + resolved presets. Lazy/uncached so a
        # loop commit landing mid-session (a running A6 flow) shows on the next call.
        md, _, _ = owner._resolve(query)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        return owner._json_resp(200, owner.states(md))

    if path == "/review/compare" and method == "GET":
        # B13.4: two banked states aligned at section/paragraph grain (the fragment-
        # stem + `% <SEC>-pN` idiom). Unknown / unresolvable state -> 422 with reason.
        md, _, _ = owner._resolve(query)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        res = owner.compare(md, owner._q1(query, "a"), owner._q1(query, "b"))
        return owner._json_resp(200 if "error" not in res else 422, res)

    if path == "/review/crop" and method == "GET":
        # the D2 visual-gate crop seam: serve a crop image fenced UNDER the
        # manuscript dir (a finding carries its crop path when one exists on disk).
        md, _, _ = owner._resolve(query)
        if md is None:
            return owner._json_resp(404, {"error": "unknown corpus / dir"})
        rel = owner._q1(query, "path")
        cand = owner._fence(md / rel) if rel else None
        if cand is None or not cand.is_file() or cand.suffix.lower() not in (
                ".png", ".jpg", ".jpeg", ".webp"):
            return owner._json_resp(404, {"error": "no such crop under the manuscript dir"})
        ctype = "image/png" if cand.suffix.lower() == ".png" else "image/jpeg"
        return 200, ctype, cand.read_bytes()

    return owner._json_resp(404, {"error": f"unknown review route {path!r}"})
