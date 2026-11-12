"""Fingerprinted suppression: a dismissed finding is dropped before the fixer
spends tokens; a materially-changed node makes its suppression STALE (judgeable
again); a wildcard record widens the suppression to every kind on the node."""
from laplace.pipeline import suppress


# --- the content fingerprint -------------------------------------------------
def test_fingerprint_stable_under_whitespace_and_comments():
    a = suppress.content_fingerprint("The map is the territory.")
    b = suppress.content_fingerprint("The   map\nis the   territory.  % a note\n")
    c = suppress.content_fingerprint("The map is the territory.  % different note")
    assert a == b == c                      # reflow / re-comment does not change it


def test_fingerprint_changes_on_substance():
    a = suppress.content_fingerprint("The map is the territory.")
    b = suppress.content_fingerprint("The map is NOT the territory.")
    assert a != b


def test_fingerprint_is_process_stable():
    # a plain str hash would be salted per process; sha256 is stable.
    assert suppress.content_fingerprint("x") == suppress.content_fingerprint("x")
    assert len(suppress.content_fingerprint("x")) == 16


# --- record shape: rides the shared feedback ledger, additive to propagate ---
def test_suppression_record_is_ledger_compatible_and_spent():
    rec = suppress.make_suppression("def:phi", "meta-leak", "The result holds.",
                                    reason="author ruled it terminal", actor="g",
                                    round=2)
    assert rec["record"] == suppress.RECORD_KIND == "suppression"
    # status resolved -> propagate.intake_items treats it as spent BEFORE the
    # unrouted-kind door, so a wildcard "*" kind never trips that gate.
    assert rec["status"] == "resolved"
    assert rec["kind"] == "meta-leak" and rec["node_id"] == "def:phi"
    assert rec["provenance"] == {"reason": "author ruled it terminal", "actor": "g",
                                 "round": 2, "fingerprint": rec["fingerprint"]}


# --- load: only active suppression records ----------------------------------
def _write(tmp_path, records):
    p = tmp_path / "feedback.jsonl"
    for r in records:
        suppress.append_suppression(p, r)
    return p


def test_load_returns_only_active_suppressions(tmp_path):
    s1 = suppress.make_suppression("def:phi", "meta-leak", "body one",
                                   reason="terminal", actor="g", round=1,
                                   rec_id="SUP-1")
    revoke = suppress.make_suppression("def:phi", "meta-leak", "body one",
                                       reason="revoked", actor="g", round=2,
                                       rec_id="SUP-2", supersedes="SUP-1")
    # a non-suppression feedback record shares the ledger and is ignored.
    finding = {"id": "F1", "record": "finding", "kind": "meta-leak",
               "node_id": "def:phi"}
    p = tmp_path / "feedback.jsonl"
    for r in (s1, finding, revoke):
        suppress.append_suppression(p, r)
    active = suppress.load_suppressions(p)
    ids = {r["id"] for r in active}
    assert ids == {"SUP-2"}                  # SUP-1 revoked; finding not a suppression


# --- filter: suppressed / kept / stale --------------------------------------
def test_finding_suppressed_when_node_kind_and_fingerprint_match(tmp_path):
    text = "This equation is a terminal result; leave it."
    s = suppress.make_suppression("res:main", "meta-leak", text,
                                  reason="terminal result", actor="g", round=1)
    p = _write(tmp_path, [s])
    supps = suppress.load_suppressions(p)
    finding = {"id": "F1", "kind": "meta-leak", "node_id": "res:main"}
    out = suppress.filter_findings([finding], supps, {"res:main": text})
    assert out["suppressed"] == [finding]
    assert out["kept"] == [] and out["stale"] == []


def test_finding_kept_when_kind_differs(tmp_path):
    text = "body"
    s = suppress.make_suppression("res:main", "meta-leak", text,
                                  reason="x", actor="g", round=1)
    p = _write(tmp_path, [s])
    supps = suppress.load_suppressions(p)
    finding = {"id": "F1", "kind": "naked-claim", "node_id": "res:main"}
    out = suppress.filter_findings([finding], supps, {"res:main": text})
    assert out["kept"] == [finding]          # different kind, not suppressed
    assert out["suppressed"] == [] and out["stale"] == []


def test_finding_kept_when_node_differs(tmp_path):
    text = "body"
    s = suppress.make_suppression("res:main", "meta-leak", text,
                                  reason="x", actor="g", round=1)
    p = _write(tmp_path, [s])
    supps = suppress.load_suppressions(p)
    finding = {"id": "F1", "kind": "meta-leak", "node_id": "res:other"}
    out = suppress.filter_findings([finding], supps,
                                   {"res:main": text, "res:other": "other"})
    assert out["kept"] == [finding]
    assert out["suppressed"] == []


def test_stale_on_content_change_reopens_the_finding(tmp_path):
    original = "This equation is a terminal result; leave it."
    s = suppress.make_suppression("res:main", "meta-leak", original,
                                  reason="terminal", actor="g", round=1,
                                  rec_id="SUP-STALE")
    p = _write(tmp_path, [s])
    supps = suppress.load_suppressions(p)
    finding = {"id": "F1", "kind": "meta-leak", "node_id": "res:main"}
    # the node was regenerated -> new content -> the suppression is stale.
    regenerated = "This equation now carries a leaked contract note."
    out = suppress.filter_findings([finding], supps, {"res:main": regenerated})
    assert out["suppressed"] == []                    # never applied
    assert out["kept"] == [finding]                   # judgeable again
    assert [r["id"] for r in out["stale"]] == ["SUP-STALE"]


def test_wildcard_widens_to_every_kind_on_the_node(tmp_path):
    text = "leave this whole node alone"
    s = suppress.make_suppression("fig:nf6", suppress.WILDCARD, text,
                                  reason="that figure is fine as-is", actor="g",
                                  round=1)
    assert s["kind"] == "*"
    p = _write(tmp_path, [s])
    supps = suppress.load_suppressions(p)
    findings = [
        {"id": "F1", "kind": "figure-purpose", "node_id": "fig:nf6"},
        {"id": "F2", "kind": "caption", "node_id": "fig:nf6"},
        {"id": "F3", "kind": "meta-leak", "node_id": "other"},
    ]
    out = suppress.filter_findings(findings, supps,
                                   {"fig:nf6": text, "other": "x"})
    assert {f["id"] for f in out["suppressed"]} == {"F1", "F2"}
    assert {f["id"] for f in out["kept"]} == {"F3"}


def test_unknown_node_text_is_kept_not_hidden(tmp_path):
    text = "body"
    s = suppress.make_suppression("res:main", "meta-leak", text,
                                  reason="x", actor="g", round=1)
    p = _write(tmp_path, [s])
    supps = suppress.load_suppressions(p)
    finding = {"id": "F1", "kind": "meta-leak", "node_id": "res:main"}
    # node absent from node_text -> cannot confirm fingerprint -> keep (re-judge).
    out = suppress.filter_findings([finding], supps, {})
    assert out["kept"] == [finding]
    assert out["suppressed"] == [] and out["stale"] == []
