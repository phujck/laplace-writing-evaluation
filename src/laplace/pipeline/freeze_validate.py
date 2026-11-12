"""freeze_validate.py — the substance-freeze validator, a durable organ.

The debt this pays (2026-07-19, the worker runs): the voiced-everywhere quarantine
(``…/2026-07-17-r6-voiced-everywhere/evidence/validate_verdict.md``) was produced by
an AD-HOC scratchpad script (``wash_validate.py``, outside the repo) — the verdict
itself names this as evidence the round used unvetted machinery. The infrastructure
law (hand-production is banned; every deliverable is a durable organ with
reproducibility as the acceptance test) requires THIS module to exist before any
further model prose lands. The method below is the banked verdict's own, landed as
code.

The three verdict layers (the quarantine's law, mechanized):

* **SUBSTANCE** (STOP — "never the validator's to make; record it and stop that
  fragment"): any delta in the FROZEN CLASSES — display-equation bodies
  (sha256_16 multiset), ``\\label`` multiset, individual ``\\cite`` keys
  (multiset), ``% PLAN`` / ``% NODES`` marker lines (byte-equal sequences),
  section-head sequence — or a touched ``main.tex`` (front matter is IDENTITY;
  a prose pass writes fragments only, the C07 clause).
* **MECHANICAL** (retry-lawful prose slips): a ``check_voice`` flag count above
  the fragment's baseline (the twin law: candidate flags ≤ baseline), or a
  meta-leak the pass INTRODUCED (``meta_leak_scrub.scrub_text`` delta).
* **BENIGN** (reported, never a fail): ``\\ref``/``\\eqref``/``\\cref`` key or
  multiplicity drift — prose referencing targets more or fewer times is language,
  not substance (the N1/N6 precedent).

``retry_lawful`` mechanizes the one-RETRY precondition: the substance freeze HELD
and only mechanical slips leaked (the r6-voiced twin precedent). A broken freeze
is never retried — the affected fragment reverts and the defect banks as a typed
record for the author.

READ-ONLY over its inputs; the only write is the optional verdict bank
(:func:`write_verdict`). Deterministic for fixed texts.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from laplace.pipeline import schema

# --------------------------------------------------------------------------- #
# the frozen-class extraction (the banked verdict's method, verbatim-in-code)
# --------------------------------------------------------------------------- #

_ENV_RE = re.compile(
    r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}(.*?)\\end\{\1\}",
    re.S)
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
_CITE_RE = re.compile(r"\\cite[tp]?\{([^}]+)\}")
_REF_RE = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref)\{([^}]+)\}")
_HEAD_RE = re.compile(r"\\(?:sub)*section\*?\{([^}]+)\}")


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def fragment_freeze(text: str) -> dict[str, Any]:
    """Extract one fragment's FROZEN CLASSES — the objects a prose pass may never
    change. Equation bodies are whitespace-normalized before hashing so a pure
    reflow of a display environment is not a false substance hit; anything that
    changes the mathematics changes the hash."""
    equations = []
    for m in _ENV_RE.finditer(text):
        body = re.sub(r"\s+", " ", m.group(2)).strip()
        equations.append(f"{m.group(1)}:{_sha16(body)}")
    cites = [k.strip() for grp in _CITE_RE.findall(text)
             for k in grp.split(",") if k.strip()]
    markers = ([m.group(0) for m in schema.PLAN_MARKER_RE.finditer(text)]
               + [m.group(0) for m in schema.NODES_MARKER_RE.finditer(text)])
    return {
        "equations": sorted(Counter(equations).items()),
        "labels": sorted(Counter(_LABEL_RE.findall(text)).items()),
        "cites": sorted(Counter(cites).items()),
        "markers": markers,
        "heads": _HEAD_RE.findall(text),
        "refs": sorted(Counter(_REF_RE.findall(text)).items()),   # BENIGN class
    }


def _multiset_delta(before: list, after: list) -> dict[str, list]:
    b, a = dict(before), dict(after)
    added = [k for k in a if a[k] > b.get(k, 0)]
    removed = [k for k in b if b[k] > a.get(k, 0)]
    return {"added": sorted(added), "removed": sorted(removed)}


def diff_fragment(before: str, after: str, *,
                  fragment: str = "<fragment>") -> dict[str, Any]:
    """One fragment's freeze diff: substance violations (STOP), mechanical slips
    (retry-lawful), benign drift (reported). Pure text-in, verdict-out."""
    fb, fa = fragment_freeze(before), fragment_freeze(after)
    substance: list[dict[str, Any]] = []
    for cls in ("equations", "labels", "cites"):
        d = _multiset_delta(fb[cls], fa[cls])
        if d["added"] or d["removed"]:
            substance.append({"class": f"{cls}-changed", **d})
    if fb["markers"] != fa["markers"]:
        substance.append({"class": "markers-changed",
                          "before": fb["markers"], "after": fa["markers"]})
    if fb["heads"] != fa["heads"]:
        substance.append({"class": "sections-changed",
                          "before": fb["heads"], "after": fa["heads"]})

    benign: list[dict[str, Any]] = []
    ref_delta = _multiset_delta(fb["refs"], fa["refs"])
    if ref_delta["added"] or ref_delta["removed"]:
        benign.append({"class": "ref-drift", **ref_delta})

    mechanical: list[dict[str, Any]] = []
    from laplace.pipeline.verify import check_voice
    vb = len((check_voice(before) or {}).get("flags") or [])
    va = len((check_voice(after) or {}).get("flags") or [])
    if va > vb:
        mechanical.append({"class": "voice-regression",
                           "baseline": vb, "candidate": va})
    from laplace.pipeline.meta_leak_scrub import scrub_text
    lb = {(h.get("class"), h.get("match")) for h in scrub_text(fragment, before)}
    la = [h for h in scrub_text(fragment, after)
          if (h.get("class"), h.get("match")) not in lb]
    if la:
        mechanical.append({"class": "meta-leak-introduced", "n": len(la),
                           "hits": [{"line": h.get("line"), "class": h.get("class"),
                                     "match": h.get("match")} for h in la[:8]]})

    return {"fragment": fragment,
            "substance": substance, "mechanical": mechanical, "benign": benign,
            "clean": not substance and not mechanical}


def _resolve_fragments(src: dict[str, str] | str | Path,
                       fragments: list[str] | None) -> dict[str, str]:
    if isinstance(src, dict):
        texts = dict(src)
    else:
        d = Path(src)
        texts = {p.stem: p.read_text(encoding="utf-8", errors="replace")
                 for p in sorted(d.glob("*.tex")) if p.name != "main.tex"}
    if fragments is not None:
        texts = {k: v for k, v in texts.items() if k in fragments}
    return texts


def validate_freeze(before: dict[str, str] | str | Path,
                    after: dict[str, str] | str | Path, *,
                    fragments: list[str] | None = None,
                    main_before: str | None = None,
                    main_after: str | None = None) -> dict[str, Any]:
    """The whole-pass verdict. ``before``/``after`` are fragment dirs or
    ``{fragment: text}`` maps (``main.tex`` excluded from a dir scan — it rides
    the identity gate instead). A fragment present on only one side is a
    SUBSTANCE violation (``fragment-added`` / ``fragment-removed`` — the NA3
    orphan precedent). Returns::

        {pass, substance_pass, mechanical_pass, retry_lawful,
         per_fragment: {...}, classes: {...}, front_matter}
    """
    tb = _resolve_fragments(before, fragments)
    ta = _resolve_fragments(after, fragments)
    per: dict[str, Any] = {}
    for name in sorted(set(tb) | set(ta)):
        if name not in ta:
            per[name] = {"fragment": name, "clean": False, "mechanical": [],
                         "benign": [],
                         "substance": [{"class": "fragment-removed"}]}
        elif name not in tb:
            per[name] = {"fragment": name, "clean": False, "mechanical": [],
                         "benign": [],
                         "substance": [{"class": "fragment-added",
                                        "note": "the NA3-orphan precedent — a "
                                                "prose pass mints no fragments"}]}
        else:
            per[name] = diff_fragment(tb[name], ta[name], fragment=name)

    front = {"checked": main_before is not None and main_after is not None,
             "identical": None}
    front_violation = False
    if front["checked"]:
        front["identical"] = main_before == main_after
        front_violation = not front["identical"]

    substance_pass = (not front_violation
                      and all(not p["substance"] for p in per.values()))
    mechanical_pass = all(not p["mechanical"] for p in per.values())
    classes: Counter = Counter()
    for p in per.values():
        for layer in ("substance", "mechanical", "benign"):
            for v in p[layer]:
                classes[v["class"]] += 1
    if front_violation:
        classes["front-matter-touched"] += 1
    return {
        "kind": "substance-freeze-verdict",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pass": substance_pass and mechanical_pass,
        "substance_pass": substance_pass,
        "mechanical_pass": mechanical_pass,
        # the ONE-RETRY law's precondition, mechanized: freeze HELD, prose slips only
        "retry_lawful": substance_pass and not mechanical_pass,
        "front_matter": front,
        "per_fragment": per,
        "classes": dict(classes),
        "law": ("substance = STOP (revert the fragment, bank the defect — never "
                "the validator's to make); mechanical = retry-lawful prose slips; "
                "benign = reported, never a fail"),
    }


def write_verdict(verdict: dict[str, Any], out_path: str | Path) -> Path:
    """Bank the verdict (json) beside the pass's products — the version-bank
    idiom's evidence file, from the ORGAN this time, not a scratchpad."""
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(verdict, indent=1, ensure_ascii=False) + "\n",
                 encoding="utf-8")
    return p
