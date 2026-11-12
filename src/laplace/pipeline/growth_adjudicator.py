"""The growth adjudicator — the bridge that makes the author-proxy the *taste
authority* inside conceptric growth.

His mandate, verbatim: *"the whole point of the adjudicator was to use it to drive
the conceptric generation loop as many of the conceptrics you start from are
fundamentally thin, and soaked in slogan slop."* So the proxy stops being a fork
organ only — it becomes the judge the growth loop consults on every taste call it
cannot make mechanically: which slop to kill, which node to deepen, whether a
register is his own or public jargon, what a thin essence truly is.

The seam is deliberate and load-bearing: **builder ≠ judge**. This module NEVER
calls a model. It assembles a decision *frame* (via :mod:`laplace.engine.author_proxy`),
attaches the growth-decision payload, and returns a DISPATCH-READY adjudication
packet. A dispatched JUDGE consumes the packet, rules, and the consumer banks that
ruling with ``kind:"growth"`` through :func:`bank_growth_ruling` — the same
append-only, decide-and-bank, contested-not-veto ledger the proxy already owns.

Three moving parts, no model call anywhere:

- :func:`adjudicate_growth` — one growth decision → one adjudication packet
  ``{frame, decision, bank}``. ``bank`` is *callable-shape docs*: it tells the
  judge exactly what a bankable ruling looks like, without this module ever writing.
  Its frame-less sibling :func:`adjudicate_growth_lite` is the MANIFEST path: when a
  whole wave shares one frame, embedding it per packet is the flatten reflex (23
  packets × the whole ruling corpus ≈ 1.2MB of duplicate) — so the lite packet keeps
  only its own decision and the shared frame is hoisted once (:func:`assemble_manifest_frame`).
- :func:`emit_dispatch_manifest` — many packets → the manifest a workflow /
  orchestrator consumes (mirrors ``storyboard``'s dispatch-manifest idiom). Pass
  ``frame=`` to bank the hoisted manifest-level frame ONCE at the top level (schema 2).
- :func:`bank_growth_ruling` — the ONLY write path: stamp ``kind:"growth"`` and
  delegate to :func:`author_proxy.bank_ruling` (schema-validated, append-only).

The harness weld — folding this callable organ into the *staged* growth workflow so
the loop calls the manifest automatically — is the NEXT session's edge. v1 offers
the organ + gate; it does not touch the pipeline stages themselves.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Iterable

from laplace.engine import author_proxy

#: the growth-decision kinds the loop can pose to the proxy. Each is a taste call a
#: mechanical gate can *surface* but not *settle* — the judge settles it.
GROWTH_KINDS: tuple[str, ...] = (
    "deslop-keep-kill-rewrite",   # a node/sentence reads as slogan slop: keep/kill/rewrite
    "deepen-which-node",          # which thin node under a subject to grow next
    "register-naming",            # is this term the author's own or public jargon
    "essence-edit",               # the essence of a node is thin: what is the truer essence
)

#: callable-shape docs travelling in every packet's ``bank`` slot — the contract a
#: dispatched judge fulfils to produce a bankable ruling. This module states the
#: shape; it never performs the write (builder ≠ judge).
BANK_CONTRACT: dict = {
    "function": "laplace.pipeline.growth_adjudicator.bank_growth_ruling",
    "signature": "bank_growth_ruling(repo_root, ruling) -> dict",
    "kind": "growth",
    "required_keys": list(author_proxy.REQUIRED_KEYS),
    "confidence_levels": sorted(author_proxy.CONFIDENCE_LEVELS),
    "id_shape": "PV-<UTCstamp>-<slug>  (via author_proxy.make_ruling_id)",
    "note": (
        "The dispatched judge returns a ruling dict carrying the required keys; the "
        "consumer calls bank_growth_ruling(repo_root, ruling), which stamps "
        "kind='growth' and appends via author_proxy.bank_ruling. Append-only, "
        "decide-and-bank, contested-not-veto: a correction is a later kind='contest' "
        "record, never an in-place edit."
    ),
}


# ------------------------------------------------------------------ question builder
def _question_for(decision: dict) -> str:
    """Turn a growth decision into the one question the assembled frame answers.
    The question is the judge's whole task statement — it names the taste call and
    the keep/kill/rewrite (or deepen/name/essence) shape of the ruling wanted."""
    kind = decision["kind"]
    subject = str(decision.get("subject", "")).strip()
    context = str(decision.get("context", "")).strip()
    cands = decision.get("candidates") or []

    if kind == "deslop-keep-kill-rewrite":
        head = (f"DESLOP — the conceptric text {subject!r} reads as slogan slop. Rule "
                f"one of: KEEP (it is genuinely his voice, not slop), KILL (excise it), "
                f"REWRITE (give the truer, grounded line). ")
    elif kind == "deepen-which-node":
        head = (f"DEEPEN — the node/region {subject!r} is thin. Name which child (or "
                f"which missing child) should be grown next, and why it earns the depth. ")
    elif kind == "register-naming":
        head = (f"NAMING — is the register/term {subject!r} the author's own coinage or "
                f"borrowed public jargon? Rule KEEP or RENAME (give his term). ")
    elif kind == "essence-edit":
        head = (f"ESSENCE — the essence of {subject!r} is thin/generic. Give the truer "
                f"essence in his voice, or KEEP if it is already his. ")
    else:  # pragma: no cover - guarded by adjudicate_growth
        head = f"GROWTH — rule on {subject!r}. "

    parts = [head]
    if cands:
        shown = " | ".join(str(c) for c in list(cands)[:8])
        parts.append(f"Candidates: {shown}. ")
    if context:
        parts.append(f"Context: {context}")
    return "".join(parts).strip()


# ------------------------------------------------------------------ the adjudication
def adjudicate_growth(repo_root: Path | str, decision: dict) -> dict:
    """One growth ``decision`` → one dispatch-ready adjudication packet.

    ``decision`` = ``{kind, subject, candidates?, context, fork_id?}`` where ``kind``
    is one of :data:`GROWTH_KINDS`. Assembles the minimal-sufficient frame via
    :func:`author_proxy.assemble_decision_frame` (profile organs, ruling corpus, prior
    verdicts, and — if ``fork_id`` is given — the fork's own rows), attaches the
    decision payload, and returns ``{frame, decision, bank}``. NEVER calls a model.
    """
    kind = decision.get("kind")
    if kind not in GROWTH_KINDS:
        raise ValueError(
            f"unknown growth kind {kind!r}; expected one of {list(GROWTH_KINDS)}")

    question = _question_for(decision)
    fork_id = decision.get("fork_id")
    frame = author_proxy.assemble_decision_frame(repo_root, question, fork_id)
    return {
        "frame": frame,
        "decision": dict(decision),
        "bank": BANK_CONTRACT,
    }


def assemble_manifest_frame(repo_root: Path | str, question: str) -> dict:
    """The one frame a whole manifest of lite packets shares — assembled once via
    :func:`author_proxy.assemble_decision_frame` from a MANIFEST-level ``question``
    (the wave's task statement, not any single packet's). The gate hoists this to the
    manifest top-level so the judge reads the shared frame once and each packet carries
    only its own decision (see :func:`adjudicate_growth_lite`). NEVER calls a model."""
    return author_proxy.assemble_decision_frame(repo_root, question)


def adjudicate_growth_lite(decision: dict) -> dict:
    """One growth ``decision`` → a FRAME-LESS packet ``{decision, bank}``.

    The lite sibling of :func:`adjudicate_growth` for the manifest path, where the
    frame is invariant across every packet in one gate run and so is hoisted to the
    manifest top-level ONCE (via :func:`assemble_manifest_frame` +
    :func:`emit_dispatch_manifest`'s ``frame=``). Rebuilding the full frame per packet
    is the flatten reflex — the whole ruling corpus duplicated 23 times. Here the packet
    keeps ONLY its own task statement: the derived ``question`` is folded into the
    returned decision dict so each packet still names its own keep/kill/rewrite call.
    Same kind-validation as :func:`adjudicate_growth`; NEVER calls a model."""
    kind = decision.get("kind")
    if kind not in GROWTH_KINDS:
        raise ValueError(
            f"unknown growth kind {kind!r}; expected one of {list(GROWTH_KINDS)}")

    dec = dict(decision)
    dec["question"] = _question_for(decision)
    return {
        "decision": dec,
        "bank": BANK_CONTRACT,
    }


# ------------------------------------------------------------------ the manifest
def emit_dispatch_manifest(packets: Iterable[dict], out_path: Path | str,
                           frame: dict | None = None) -> dict:
    """Write the dispatch manifest a growth workflow/orchestrator consumes.

    Mirrors ``storyboard``'s dispatch-manifest idiom: a single self-describing JSON
    (``kind`` / ``count`` / ``cut_at`` / ``invocation`` / the ``bank_contract`` every
    consumer honours) with the packets embedded — the judge reads the packet's frame
    to rule. Returns the manifest dict; the file at ``out_path`` is the same content.

    When ``frame`` is given (the manifest-level frame the lite packets share, from
    :func:`assemble_manifest_frame`), it is banked ONCE at the top level: the manifest
    gains a ``"frame"`` and ``"schema": 2``, and the judge reads the shared frame plus
    each packet's own decision. Without ``frame`` the legacy shape (frame per packet)
    is written unchanged — nothing mechanically consumes the old shape, so this is
    additive and safe.
    """
    packet_list = list(packets)
    manifest = {
        "kind": "growth-adjudication",
        "count": len(packet_list),
        "cut_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "bank_contract": BANK_CONTRACT,
        "packets": packet_list,
        # the invocation the local judge leg runs (the LLM leg lives outside python)
        "invocation": None,
    }
    if frame is not None:
        # the hoisted, shared frame — banked once here, not duplicated per packet
        manifest["schema"] = 2
        manifest["frame"] = frame
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest["invocation"] = f'/growth-adjudicate --manifest "{out.name}"'
    out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    return manifest


# ------------------------------------------------------------------ the only write
def bank_growth_ruling(repo_root: Path | str, ruling: dict) -> dict:
    """Bank a growth ruling: stamp ``kind:"growth"`` and delegate to
    :func:`author_proxy.bank_ruling` (schema-validated, append-only to
    ``proxy_verdicts.jsonl``). Returns the banked record. The ``ruling`` must carry
    the proxy's required spine (see :data:`BANK_CONTRACT`)."""
    rec = dict(ruling)
    rec["kind"] = "growth"
    return author_proxy.bank_ruling(repo_root, rec)


def new_growth_ruling_id(subject: str) -> str:
    """Convenience: a ``PV-<stamp>-<slug>`` id for a growth ruling, slugged from the
    subject — so a judge/consumer need not reach into ``author_proxy`` directly."""
    return author_proxy.make_ruling_id(f"growth-{subject}")


# a tiny type alias documenting the judge leg this module deliberately omits.
JudgeLeg = Callable[[dict], dict]  # (packet) -> ruling  — dispatched, never called here
