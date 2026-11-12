"""C2 — the citation apparatus + coverage gate (checklist cat 4).

Gerard's standing annoyance is *information thrown around without being cited*.
This gate runs the two conjugate sweeps:

**Backward** (reuse, not rebuild): :func:`laplace.pipeline.verify.check_corpus_citations`
already checks that every reference a *project* declares it relies on
(``provenance`` in ``corpus.bib``) is actually ``\\cite``d in the manuscript. Its
naked reliances become ``citation-naked-reliance`` findings.

**Forward** (the gap): a sweep from the prose *outward*. Every
externally-grounded-shaped assertion — a historical/priority claim, a
prior-method description, a complexity scaling, a hardware/experimental figure,
an imported theorem/bound, a "what existing approaches require/achieve" —
carries a *tell* ("was shown", "is known", "scales as", "requires", "achieves",
a named method/hardware, a bare number-with-units). A tell sitting near no
``\\cite`` is flagged ``citation-uncited``. This is the **mechanical floor**: the
semantic original-vs-inherited call (does *this* sentence need a cite, or is it
the paper's own contribution?) is R2/R3's job in Phase E — the floor annotates
whether first-person original markers are present so that reader can triage.

Plus the apparatus reductions: the **claim-to-source table** (from the Phase-A
``claim → cites`` edges), **cluster-role splitting** (an end-of-paragraph
cite-everything ``\\cite{a,b,c,d}`` that should be split to the specific claim
each key supports), and **first-use placement** (a key whose first appearance is
inside a cluster rather than at its first substantive mention).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline.graph import CanonGraph, _CITE_RE, _gather_manuscript_text
from laplace.pipeline.apparatus_common import (
    finding, iter_paragraphs, iter_sentences, line_quote, section_of,
    section_spans, summarise,
)

# --- the external-fact tells (the mechanical floor) --------------------------
# STRONG tells name outside knowledge outright — flagged near no \cite whether or
# not the sentence is first-person (the paper's own numerics still cite the named
# method / prior result they lean on).
_STRONG_TELLS = re.compile(
    r"\b("
    r"was shown|were shown|has been shown|have been shown|it is known|are known|is known|"
    r"was demonstrated|were demonstrated|has been demonstrated|"
    r"was proved|was proven|were proven|it was established|it has been established|"
    r"prior work|previous work|earlier work|existing (?:approaches|methods|schemes|work)|"
    r"state[- ]of[- ]the[- ]art|in the literature|widely used|well[- ]known|classic(?:al)? result|"
    r"known to (?:scale|require|be)"
    r")\b", re.I)
# Named-hardware / named-method tells — a named external method/device should
# cite its source even inside the paper's own use of it.
_NAMED_TELLS = re.compile(
    r"\b("
    r"phase[- ]estimation|Trotter(?:isation|ization)?|VQE|QPE|QAOA|Lanczos|Krylov|"
    r"meet[- ]in[- ]the[- ]middle|Howgrave[- ]Graham|Joux|quantum[- ]walk|"
    r"DMRG|matrix[- ]product[- ]state|surface[- ]code|transmon|magic[- ]state"
    r")\b")
# Bare number-with-units — an experimental/hardware figure asserted flatly.
_UNIT_TELLS = re.compile(
    r"\b\d[\d.,]*\s*(?:kHz|MHz|GHz|ns|µs|ms|T[- ]gates?|dB|mK|meV)\b")
# WEAK tells — external-shaped but common enough to fire on the paper's own work;
# flagged only when NO first-person original marker sits in the same sentence.
_WEAK_TELLS = re.compile(
    r"\b("
    r"conventional(?:ly)?|standard(?: approaches| methods| techniques)|"
    r"scales? as|scaling of|grows? as|goes? as|"
    r"is bounded by|are bounded by|upper[- ]bounded|lower[- ]bounded|"
    r"require[s]?|need[s]?|achieve[s]?|attain[s]?"
    r")\b", re.I)
# Complexity-scaling forms — weak (the paper states its own scalings too).
_COMPLEXITY_TELLS = re.compile(r"(?:\bO\s*\(|\b2\^|\bNP[- ]hard)")
# First-person / original-contribution markers — down-weight the WEAK tells.
_ORIGINAL_MARK = re.compile(
    r"\b(we\s+\w+|our\s+(?:method|approach|result|construction|reconstruction|benchmark|"
    r"derivation|analysis)|here we|in this (?:paper|work)|the present (?:method|work)|"
    r"the method (?:reads|reconstructs|removes|carries)|SSG\b)", re.I)


def _cites_in(text: str) -> set[str]:
    keys: set[str] = set()
    for m in _CITE_RE.finditer(text):
        keys |= {k.strip() for k in m.group(1).split(",") if k.strip()}
    return keys


def _forward_sweep(full: str, spans) -> list[dict[str, Any]]:
    """Flag every external-fact tell sitting near no ``\\cite``. Near = the same
    sentence or the sentence immediately after (a cite often trails the claim)."""
    out: list[dict[str, Any]] = []
    for p_start, _p_end, para in iter_paragraphs(full):
        # skip pure-environment blocks (figures, equations, tabular) — those are
        # apparatus, not prose assertions.
        if re.match(r"\s*\\(begin|includegraphics|input)\b", para):
            continue
        sents = list(iter_sentences(para))
        for i, (off, sent) in enumerate(sents):
            original = bool(_ORIGINAL_MARK.search(sent))
            tells: list[str] = []
            # strong tells + named methods + bare figures fire regardless of voice
            for rx, name in ((_STRONG_TELLS, None), (_NAMED_TELLS, "named-method"),
                             (_UNIT_TELLS, "bare-figure")):
                m = rx.search(sent)
                if m:
                    tells.append(name or m.group(1).lower())
            # weak / complexity tells fire only when the sentence is NOT the
            # paper speaking about its own work (R2 owns the semantic call above
            # this floor)
            if not original:
                for rx, name in ((_WEAK_TELLS, None), (_COMPLEXITY_TELLS, "complexity-scaling")):
                    m = rx.search(sent)
                    if m:
                        tells.append(name or (m.group(1).lower() if m.groups() else "complexity-scaling"))
            if not tells:
                continue
            # a cite in this sentence or the next one grounds it
            window = sent + (sents[i + 1][1] if i + 1 < len(sents) else "")
            if _cites_in(window):
                continue
            pos = p_start + off
            slug, _title, _app = section_of(pos, spans)
            note = " (first-person markers present — R2 to confirm it is the paper's own contribution)" if original else ""
            out.append(finding(
                f"{slug or '?'}",
                f"external-fact tell [{', '.join(sorted(set(tells)))}] with no nearby \\cite{note}",
                "cite the source at first substantive use, or mark it explicitly as this paper's own result",
                "citation-uncited", quote=sent.strip()))
    return out


def _cluster_sweep(full: str, spans) -> list[dict[str, Any]]:
    """End-of-paragraph cite-everything clusters: a single ``\\cite`` of >=3 keys,
    or two adjacent ``\\cite`` commands in the paragraph's last sentence."""
    out: list[dict[str, Any]] = []
    for p_start, _p_end, para in iter_paragraphs(full):
        cite_ms = list(_CITE_RE.finditer(para))
        if not cite_ms:
            continue
        tail_start = max(0, len(para) - 320)
        for m in cite_ms:
            keys = [k.strip() for k in m.group(1).split(",") if k.strip()]
            in_tail = m.start() >= tail_start
            if len(keys) >= 3 and in_tail:
                slug, _t, _a = section_of(p_start + m.start(), spans)
                out.append(finding(
                    f"{slug or '?'}",
                    f"end-of-paragraph cluster cites {len(keys)} keys at once ({', '.join(keys[:4])}{'…' if len(keys) > 4 else ''})",
                    "split the cluster — attach each key to the specific claim it supports (cluster-role splitting)",
                    "citation-cluster", quote=line_quote(para, m.start())))
    return out


def _first_use_sweep(full: str, spans, clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A citation key whose FIRST appearance in reading order is inside a cluster
    (>=3-key \\cite) rather than at its own first substantive mention."""
    first_pos: dict[str, int] = {}
    first_in_cluster: dict[str, bool] = {}
    for m in _CITE_RE.finditer(full):
        keys = [k.strip() for k in m.group(1).split(",") if k.strip()]
        is_cluster = len(keys) >= 3
        for k in keys:
            if k not in first_pos:
                first_pos[k] = m.start()
                first_in_cluster[k] = is_cluster
    out: list[dict[str, Any]] = []
    for k, pos in first_pos.items():
        if first_in_cluster.get(k):
            slug, _t, _a = section_of(pos, spans)
            out.append(finding(
                f"{slug or '?'}:{k}",
                f"citation '{k}' first appears inside a multi-key cluster, not at its own first substantive use",
                "introduce the key at the specific claim it grounds before (or instead of) folding it into a cluster",
                "citation-first-use"))
    return out


def _claim_to_source(g: CanonGraph, full: str) -> dict[str, list[str]]:
    """The claim → cited-keys table — the apparatus map R2/R3 read (a data
    product, not a finding).

    The primary source is the Phase-A ``claim → cites`` edges. For a manuscript
    that numbers its claims as semantic-prefix equations (SSG's ``def:``/``res:``
    /``irf:``/``thm:``), the cite rarely sits *inside* the equation body, so those
    edges are sparse; the table is enriched with the citations that share the
    claim's paragraph in the flattened prose, keyed by the claim's
    ``reading_order``. Every claim node appears, so an empty list is itself the
    signal (a numbered claim leaning on nothing cited nearby)."""
    # paragraph spans, so a claim's reading_order maps to the cites around it
    paras: list[tuple[int, int, set[str]]] = []
    for p_start, p_end, para in iter_paragraphs(full):
        paras.append((p_start, p_end, _cites_in(para)))

    def cites_near(order: int) -> set[str]:
        for s, e, keys in paras:
            if s <= order < e:
                return keys
        return set()

    claims = {nid: n for nid, n in g.nodes.items() if n.kind == "claim"}
    table: dict[str, list[str]] = {cid: [] for cid in claims}
    for e in g.edges:
        if e.rel == "cites" and e.src in claims:
            key = g.nodes[e.dst].meta.get("key", e.dst)
            if key not in table[e.src]:
                table[e.src].append(key)
    for cid, n in claims.items():
        for key in sorted(cites_near(n.meta.get("reading_order", -1))):
            if key not in table[cid]:
                table[cid].append(key)
    return table


def check_citation_audit(target: Union[str, Path],
                         corpus_path: Optional[Union[str, Path]] = None,
                         project: Optional[str] = None) -> dict[str, Any]:
    """Both citation sweeps on a compiled manuscript.

    ``corpus_path``/``project`` drive the backward sweep
    (:func:`check_corpus_citations`); when unavailable that half reports
    ``manual`` and only the forward sweep runs."""
    target = Path(target)
    full = _gather_manuscript_text(target)
    g = CanonGraph.from_manuscript(target)
    spans = section_spans(full)

    findings: list[dict[str, Any]] = []

    # --- backward: reuse the corpus-citations gate ---------------------------
    backward: dict[str, Any] = {"status": "skipped"}
    if corpus_path and project:
        from laplace.pipeline.verify import check_corpus_citations
        try:
            bw = check_corpus_citations(target, corpus_path, project)
            backward = {"status": "ran", "relied_on": bw["relied_on"],
                        "surfaced": bw["surfaced"], "naked": len(bw["naked_reliances"])}
            for nk in bw["naked_reliances"]:
                where = f"bibliography:{nk['ref']}"
                state = "in the bibliography but never \\cite'd in the body" if nk["in_bib"] else "absent from the manuscript bibliography entirely"
                findings.append(finding(
                    where,
                    f"project relies on '{nk['ref']}' ({nk.get('claim','')[:80]}) but it is {state}",
                    "add the \\cite at the point the manuscript leans on this reference (or drop the reliance)",
                    "citation-naked-reliance"))
        except Exception as e:  # noqa: BLE001 — a bib parse failure is a manual signal, not a crash
            backward = {"status": "error", "error": str(e)}

    # --- forward: the tell scan + clusters + first-use -----------------------
    fwd = _forward_sweep(full, spans)
    clusters = _cluster_sweep(full, spans)
    first_use = _first_use_sweep(full, spans, clusters)
    findings += fwd + clusters + first_use

    return {
        "pass": not findings,
        "backward": backward,
        "n_forward": len(fwd),
        "n_clusters": len(clusters),
        "n_first_use": len(first_use),
        "claim_to_source": _claim_to_source(g, full),
        "findings": findings,
        "counts": summarise(findings),
    }
