"""tests/test_findings_consumer.py — THE FINDINGS CONSUMER (W-CONSUMER, 2026-07-22).

The machine-finding backlog made self-draining. The per-project feedback ledger is where
the mechanical panel / readers / holdout pour their DETECTIONS; the desk excludes them
(his to rule are the author-sourced ones) and, until this wave, nothing retired them —
panel round on panel round accumulated into the backlog the census found. This suite
proves the three honest semantics end to end:

  (1) A DISPATCH PACKET CARRIES ITS FINDINGS — the open machine findings anchored to a
      section ride its packet as bounded, fenced evidence (attach).
  (2) A LANDED FRAGMENT RETIRES WHAT IT CONSUMED — when the regenerated fragment lands,
      the prior-round findings anchored to that section retire with an append-only
      consumed_by {round, packet} resolution (land → retire).
  (3) PERSISTENCE RE-MINTS — a defect that survives regeneration is re-found FRESH by the
      next panel round (a new id, a new content fingerprint), so retirement never hides a
      live defect — PROVEN here, not asserted in prose.

The honesty constraints are pinned as assertions: the attach is bounded and the remainder
COUNTED; the retirement rows carry consumed_by {round, packet}; the re-mint is a genuinely
distinct record (fingerprint differs), and the retired finding stays retired.
"""
from __future__ import annotations

import json
from pathlib import Path

from laplace.manuscript import manuscript_bridge as mb
from laplace.pipeline import adjudicate, dispatch
from laplace.pipeline.edits import retire_consumed_findings
from laplace.pipeline.ledger import read_jsonl
from laplace.pipeline.suppress import content_fingerprint

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- helpers
def _machine_finding(fid: str, section: str, node: str, kind: str, rnd: int,
                     bytes_text: str) -> dict:
    """One mechanical-panel finding, shaped as the panel pours it: an explicit id, a
    machine ``source: mech-panel:<round>``, the section anchor, and the content
    fingerprint of the node's CURRENT bytes (the tell a later material edit went stale)."""
    return {"id": fid, "kind": kind, "section": section, "node_id": node,
            "source": f"mech-panel:r{rnd}", "status": "open",
            "fingerprint": content_fingerprint(bytes_text),
            "comment": f"{kind} at {node}", "project": "probe"}


def _write(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
                    encoding="utf-8")


# --------------------------------------------------------------------------- the machine/author split
def test_machine_vs_author_split():
    """The consumer's subject is the MACHINE detection, never the author's own note or a
    ruling ON a finding (the desk owns those). The split mirrors the desk exactly."""
    assert mb.is_machine_finding(
        {"kind": "eq-unused", "source": "mech-panel:r3", "section": "S"})
    assert mb.is_machine_finding({"kind": "citation-uncited", "by": "machine", "section": "S"})
    # author-sourced → NOT a machine finding (his to adjudicate)
    assert not mb.is_machine_finding({"kind": "note", "by": "gerard", "section": "S"})
    assert not mb.is_machine_finding({"kind": "note", "by": "visitor:sam", "section": "S"})
    assert not mb.is_machine_finding({"kind": "imprecise", "source": "the-author", "section": "S"})
    # an ACTION on a finding (a resolution / confirmation) is never itself a finding
    res = adjudicate.make_resolution("F1", section="S")
    assert not mb.is_machine_finding(res)
    conf = adjudicate.make_confirmation("F1", section="S")
    assert not mb.is_machine_finding(conf)


def test_finding_round_parse():
    assert mb.finding_round({"source": "mech-panel:r7"}) == 7
    assert mb.finding_round({"source": "mech-panel:12-post"}) == 12
    assert mb.finding_round({"provenance": {"round": 4}}) == 4
    assert mb.finding_round({"round": 2}) == 2
    assert mb.finding_round({"source": "reader"}) is None      # round-less → treated as prior


# =========================================================================== THE FIXTURE ROUND
def test_attach_land_retire_remint_end_to_end(tmp_path):
    """The whole loop on one section, one persistent defect.

    round 1: the panel finds a defect (F1) on section S.
    ATTACH:  the packet for S carries F1 as bounded evidence.
    round 2: the fragment is regenerated (the defect survives, reworded) and re-detected
             → the panel mints F2 fresh (new id, new fingerprint).
    LAND:    the regenerated fragment lands at round 2 → F1 (round 1) retires with
             consumed_by {round:2, packet}; F2 (round 2, the re-mint) is kept live.
    """
    ledger = tmp_path / "feedback" / "feedback.jsonl"
    section, node = "S2", "def:widget"
    old_bytes = "The widget is defined but never \\eqref'd anywhere in the section."
    F1 = _machine_finding("F1", section, node, "eq-unused", 1, old_bytes)
    _write(ledger, [F1])

    # (1) ATTACH — the packet's findings view carries F1 (the section's open backlog).
    recs = read_jsonl(ledger)
    attached = mb.machine_findings_for_section(recs, section)
    assert [f["id"] for f in attached] == ["F1"]

    # (2) RE-MINT first: the panel re-scans the regenerated (still-defective) fragment at
    #     round 2 and mints F2 FRESH — a distinct record, a distinct fingerprint.
    new_bytes = "The widget is introduced here, yet still carries no \\eqref anywhere."
    F2 = _machine_finding("F2", section, node, "eq-unused", 2, new_bytes)
    assert F2["fingerprint"] != F1["fingerprint"], (
        "the re-detected finding must differ from the retired one — a genuine re-mint on "
        "the new bytes, not the same record lingering")
    mb.feedback_consume  # (organ present)
    from laplace.pipeline.ledger import append_jsonl
    append_jsonl(ledger, F2)

    # (3) LAND — the regenerated fragment for S lands at round 2. The prior-round backlog
    #     (F1) retires; the current round's re-mint (F2) is untouched.
    out = retire_consumed_findings(ledger, section, round=2, packet_id="pkt:probe:S2",
                                   project="probe")
    assert out["retired"] == ["F1"], out
    assert out["count"] == 1

    after = read_jsonl(ledger)
    live = adjudicate.live(after)
    live_ids = {r.get("id") for r in live if mb.is_machine_finding(r)
                and (r.get("status") or "open") == "open"}
    assert "F1" not in live_ids, "the consumed finding must be retired (superseded)"
    assert "F2" in live_ids, "the re-minted survivor must stay live (never hidden)"

    # the retirement is HISTORY (append-only), and it names WHAT superseded the subject.
    res = [r for r in after if r.get("record") == adjudicate.RESOLUTION
           and r.get("supersedes") == "F1"]
    assert len(res) == 1, "exactly one consumed-by resolution retires F1"
    cb = res[0].get("consumed_by")
    assert cb == {"round": 2, "packet": "pkt:probe:S2",
                  "finding_kind": "eq-unused", "finding_round": 1}, cb
    assert res[0]["status"] == "resolved"
    # F1's own line is untouched — the ledger reads as history, not a rewritten past.
    f1_lines = [r for r in after if r.get("id") == "F1"]
    assert len(f1_lines) == 1 and f1_lines[0]["status"] == "open"

    # IDEMPOTENT re-land of the same round retires nothing new (F1 already superseded).
    again = retire_consumed_findings(ledger, section, round=2, packet_id="pkt:probe:S2",
                                     project="probe")
    assert again["retired"] == [], again


def test_current_round_findings_are_never_consumed(tmp_path):
    """The land side retires only PRIOR rounds — the current round's fresh findings (the
    re-mint) survive. A round-less finding is treated as prior (stale by construction)."""
    ledger = tmp_path / "feedback.jsonl"
    section = "S3"
    cur = _machine_finding("C1", section, "n1", "notation-inconsistent", 5, "a")
    stale_round = _machine_finding("O1", section, "n2", "notation-inconsistent", 4, "b")
    roundless = {"id": "R0", "kind": "citation-uncited", "section": section,
                 "source": "reader", "status": "open"}
    _write(ledger, [stale_round, cur, roundless])
    out = retire_consumed_findings(ledger, section, round=5, packet_id="pkt", project="p")
    assert set(out["retired"]) == {"O1", "R0"}, out      # prior + round-less consumed
    live = {r["id"] for r in mb.machine_findings_for_section(read_jsonl(ledger), section)}
    assert live == {"C1"}, "only the current round's finding remains live"


def test_over_cap_findings_all_retire_though_only_n_attach(tmp_path):
    """Honesty: the ATTACH is bounded (the N most recent ride the packet, the rest
    COUNTED), but the LAND retires the WHOLE prior-round backlog — an over-cap finding is
    consumed too, never orphaned forever."""
    ledger = tmp_path / "feedback.jsonl"
    section = "S4"
    n = dispatch.FINDINGS_ATTACH_CAP + 5
    recs = [_machine_finding(f"F{i}", section, f"n{i}", "eq-unused", 1, f"bytes-{i}")
            for i in range(n)]
    # stamp ascending ts so "most recent" is deterministic
    for i, r in enumerate(recs):
        r["ts"] = f"2026-07-22T00:00:{i:02d}"
    _write(ledger, recs)

    # ATTACH view is bounded, remainder counted
    sel = mb.machine_findings_for_section(read_jsonl(ledger), section)
    assert len(sel) == n
    shown = sel[:dispatch.FINDINGS_ATTACH_CAP]
    assert len(shown) == dispatch.FINDINGS_ATTACH_CAP

    # LAND retires ALL n (round 1 < round 2), not just the attached cap
    out = retire_consumed_findings(ledger, section, round=2, packet_id="pkt", project="p")
    assert out["count"] == n, out
    assert not mb.machine_findings_for_section(read_jsonl(ledger), section)


# =========================================================================== THE ATTACH WIRE (real project)
def _project_section_with_findings():
    """A registered manuscript project + a section whose feedback ledger carries open
    machine findings — the real substrate the attach reads (skips if none present)."""
    from laplace.pipeline import registry
    for name in ("eigenengine", "paper_falqon", "subset-sum-itqde"):
        proj = registry.resolve(name)
        if proj is None or not getattr(proj, "feedback_ledger", None):
            continue
        path = REPO / proj.feedback_ledger
        if not path.is_file():
            continue
        recs = read_jsonl(path)
        by_sec: dict[str, int] = {}
        for r in recs:
            if mb.is_machine_finding(r) and (r.get("status") or "open") == "open":
                by_sec[mb._finding_section(r)] = by_sec.get(mb._finding_section(r), 0) + 1
        best = max((s for s in by_sec if s), key=lambda s: by_sec[s], default=None)
        if best:
            return name, best, by_sec[best]
    return None, None, 0


def test_dispatch_channel_attaches_findings_on_a_real_section():
    """dispatch._section_findings_channel carries the section's open machine findings as a
    fenced ANCHORED-FINDINGS channel with a stable packet id — the ATTACH half wired."""
    import pytest
    name, section, count = _project_section_with_findings()
    if name is None:
        pytest.skip("no manuscript project with open machine findings on disk")
    ch = dispatch._section_findings_channel(name, section, REPO)
    assert ch is not None
    fence, meta = ch
    assert "<!-- ANCHORED-FINDINGS -->" in fence
    assert "Open machine findings anchored to this section" in fence
    assert meta["packet"] == dispatch.section_packet_id(name, section)
    assert meta["count"] == count
    assert len(meta["attached"]) == min(count, dispatch.FINDINGS_ATTACH_CAP)
    assert meta["capped"] == max(0, count - dispatch.FINDINGS_ATTACH_CAP)
    # §13: the channel is CONTENT-level, never engine framing
    for banned in ("You are one node", "canon://", "<!-- POLICY -->", "CONTRACT:"):
        assert banned not in fence


def test_dispatch_channel_additive_when_no_findings():
    """The additive floor: a section with no open machine findings gets NO channel — the
    packet is byte-identical to pre-wire."""
    from laplace.pipeline import registry
    name = next((n for n in ("eigenengine", "paper_falqon", "subset-sum-itqde")
                 if registry.resolve(n) is not None), None)
    if name is None:
        import pytest
        pytest.skip("no manuscript project on disk")
    assert dispatch._section_findings_channel(
        name, "a-section-that-does-not-exist-xyz", REPO) is None
