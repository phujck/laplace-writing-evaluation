"""The readability gate: a whole-object stranger read whose refusal blocks the lock.

Born from the r2 verdict (``evidence/FIRST_CHAIR_2026-07-21_r2-read.md``): every
structural judge stayed silent on an unreadable paper, so judge silence was mistaken
for quality. His sharpened ruling made the gate a whole-object reader, immune to
confected local passes: a stranger reads the artefact front to back as a self-contained
object and answers one question -- would a person read this, and would they be right to.
Local closure counts for nothing at this gate; a paper can pass every local judge and
still be a paper no reader would keep.

The gate reads the finished object, not the blueprint: the compiled PDF's extracted
text when a PDF is bound, else the full tex flattened along its input tree (the reading
order a stranger actually meets). It grades five things and names every breach with its
location:

  (a) a real introduction that teaches the subject before the paper prices it -- context,
      motivation, a contribution statement;
  (b) every symbol and term defined before it is used;
  (c) an arc: a thesis held across the paper, with sections that earn it, not audit rows
      in sequence;
  (d) plain subject register in the prose, free of engine-register leakage -- provenance
      narration (custody talk about how a number was obtained), config-style quantity
      names read aloud, and per-number hedging tics;
  (e) figures and references present where the argument leans on them.

Verdict is one of ``PASS`` / ``FAIL`` / ``UNAVAILABLE``. A breach of any of (a)-(d) is a
FAIL. The whole-object judgement is made by a dispatched hold-out reader (a model call at
gate time); a mechanical floor (:func:`structural_floor`) runs first and can raise the
concrete r2 breach signals on its own, so the good structural shape is graded even before
the reader speaks. When no reader model is reachable the gate returns ``UNAVAILABLE`` and
the lock path treats that as blocking -- a paper whose readability could not be checked
never locks. Fail closed, so an unreadable-unknown is refused rather than admitted.

The dispatch discipline (his 2026-07-11 ruling, carried by ``compile_dispatch``): a
dispatched reader is opus-level or less, and the model is stamped explicitly, never
inherited. :func:`compile_read_dispatch` stamps ``model`` / ``effort`` from a clamped
constant (``schema.clamp_model``) so the stamp is always at or below the ceiling. The
model call itself is a boundary the caller supplies (the orchestrator's hold-out reader
runner); this module packages the read and parses the reply and does not reach a model on
its own -- the reader-suite package-and-parse shape, so the model layer can be stubbed at
the boundary in a test without a real call.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Optional, Union

from laplace.pipeline import schema

# --- verdict labels ---------------------------------------------------------
PASS = "PASS"
FAIL = "FAIL"
UNAVAILABLE = "UNAVAILABLE"

#: the breach classes the reader grades; (a)-(d) force a FAIL, (e) is reported.
BREACH_CLASSES = ("a", "b", "c", "d", "e")
FAIL_FORCING_CLASSES = frozenset({"a", "b", "c", "d"})

#: the reader's model stamp -- explicit and clamped to the dispatch ceiling, so it is
#: always opus-level or less and never inherited from the orchestrator. A whole-object
#: judge whose refusal blocks a lock is adjudication-grade, so it earns the ceiling; the
#: caller may pass a leaner stranger proxy, which :func:`compile_read_dispatch` re-clamps.
GATE_MODEL = schema.clamp_model("opus")
GATE_EFFORT = "high"

#: cap on the artefact text handed to the reader; a longer read is marked truncated so a
#: partial read is never mistaken for a whole-object one (silence never reads as a pass).
DEFAULT_MAX_INPUT_CHARS = 200_000


# ---------------------------------------------------------------------------
# 1. Read the whole object -- the compiled PDF, else the full tex
# ---------------------------------------------------------------------------

def read_whole_artefact(manuscript_dir: Union[str, Path], *,
                        max_input_chars: int = DEFAULT_MAX_INPUT_CHARS) -> dict[str, Any]:
    """The whole-object text of the finished artefact and where it came from.

    The compiled PDF is tried first, through ``restart_reader.extract_artefact_text``
    (which binds the final PDF via ``release._discover_final_pdf`` and pulls text with
    the isolated pypdfium2 subprocess, poppler as the fallback). When no PDF is bound or
    no extractor works, the full tex is gathered instead -- flattened along the input
    tree of ``main.tex`` when a root is present (true reading order), else the sorted-glob
    merge of the directory. Returns ``{text, source, truncated, error}`` where ``source``
    is ``"pdf"`` / ``"tex"`` / ``None`` and ``error`` names why a source was skipped. An
    empty ``text`` means neither source produced a readable object.
    """
    md = Path(manuscript_dir)
    text = ""
    source: Optional[str] = None
    error: Optional[str] = None

    # 1. the finished PDF
    try:
        from laplace.pipeline.readers import restart_reader
        text = restart_reader.extract_artefact_text(md)
        source = "pdf"
    except Exception as exc:                     # no PDF bound, or no extractor -- fall through
        error = str(exc)
        text = ""

    # 2. the full tex, when the PDF gave nothing
    if not text.strip():
        try:
            from laplace.pipeline.graph import _gather_manuscript_text
            root = md / "main.tex"
            gathered = _gather_manuscript_text(root if root.is_file() else md)
            if gathered.strip():
                text, source, error = gathered, "tex", None
        except Exception as exc:
            tex_err = f"tex fallback: {exc}"
            error = f"{error}; {tex_err}" if error else tex_err

    truncated = len(text) > max_input_chars
    return {"text": text[:max_input_chars], "source": source,
            "truncated": truncated, "error": error}


# ---------------------------------------------------------------------------
# 2. The mechanical floor -- the concrete r2 breach signals, no model
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"\\(?:section|chapter)\*?\s*\{([^}]*)\}")
_INTRO_TITLE_RE = re.compile(r"introduction|background|motivation|overview|preliminaries",
                             re.IGNORECASE)

#: provenance / custody narration -- prose that reports how a number was obtained rather
#: than using it. Each phrase is drawn from the r2 read of the falqon paper.
_PROVENANCE_LEXICON: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("derived-not-assumed", re.compile(r"\bderived rather than assumed\b", re.IGNORECASE)),
    ("assumed-not-derived", re.compile(r"\bassumed rather than derived\b", re.IGNORECASE)),
    ("declared-arbitrariness", re.compile(r"\bdeclared arbitrariness\b", re.IGNORECASE)),
    ("on-the-table", re.compile(r"\bon the table rather than hidden\b", re.IGNORECASE)),
    ("tier-labels-describe", re.compile(r"\btier labels?\b[^.]{0,40}\bdescribe how\b", re.IGNORECASE)),
    ("how-number-obtained", re.compile(r"\bhow (?:a|the) number was (?:obtained|derived|computed)\b", re.IGNORECASE)),
    ("not-a-claim-about", re.compile(r"\bnot (?:a|any) claim about its objective\b", re.IGNORECASE)),
    ("this-count-is-derived", re.compile(r"\bthis (?:count|number|value) is (?:derived|assumed|computed)\b", re.IGNORECASE)),
)

#: per-number hedging tics -- caveats worn as a disclaimer on nearly every claim.
_HEDGING_LEXICON: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("not-measured-here", re.compile(r"\b(?:swept but )?not measured here\b", re.IGNORECASE)),
    ("not-checked", re.compile(r"\bhas not been checked\b", re.IGNORECASE)),
    ("no-bound-computed", re.compile(r"\bno .{0,30}? (?:bound|error) is computed\b", re.IGNORECASE)),
    ("swept-but-not", re.compile(r"\bswept but not\b", re.IGNORECASE)),
)

#: config-style quantity narrated in prose -- a snake_case store id set to a number, the
#: store's quantity ids leaking into the sentence line.
_LEDGER_NAME_RE = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\s*=\s*\d")

#: math spans to drop before the prose scan, so a legitimate symbol inside an equation is
#: never read as prose leakage.
_MATH_SPANS = (
    re.compile(r"\$\$.*?\$\$", re.DOTALL),
    re.compile(r"\\\[.*?\\\]", re.DOTALL),
    re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{\1\*?\}", re.DOTALL),
    re.compile(r"\$[^$]*\$"),
)

_HEDGING_DENSITY_FLOOR = 3          # this many distinct hedging hits reads as a per-number tic


def _strip_math(text: str) -> str:
    for pat in _MATH_SPANS:
        text = pat.sub(" ", text)
    return text


def _mechanism(cls: str, where: str, finding: str, quote: str = "") -> dict[str, str]:
    """One named breach in the standard shape: its class, where it sits, the finding,
    and a short quote when there is one."""
    return {"class": cls, "where": where, "finding": finding, "quote": quote}


def structural_floor(text: str, *, source: Optional[str] = None) -> list[dict[str, str]]:
    """The mechanical grader: the concrete r2 breach signals a stranger read would name,
    detected without a model. Conservative by design -- it fires only on strong,
    documented signals, because a false breach here blocks a lock. Returns a list of
    mechanisms (possibly empty); the caller folds these into the verdict alongside the
    reader's own findings.

    It covers the classes a mechanical scan can carry:

      * **(a) no introduction beat** -- the paper carries no section that teaches the
        subject (no introduction / background / motivation / overview / preliminaries
        heading). The r2 plan opened straight into content with none.
      * **(d) provenance narration** -- prose that reports how a number was obtained
        (:data:`_PROVENANCE_LEXICON`), the custody papers a reader does not want.
      * **(d) ledger names as prose** -- a snake_case store id set to a number in the
        sentence line (:data:`_LEDGER_NAME_RE`), a config file narrated aloud.
      * **(d) per-number hedging** -- caveats worn on nearly every claim
        (:data:`_HEDGING_LEXICON`), counted; a run of them kills momentum.

    Definitions before use (b), the arc (c), and figure support (e) are left to the
    whole-object reader, which sees the running text a scan cannot judge.
    """
    mechanisms: list[dict[str, str]] = []
    if not text.strip():
        return mechanisms

    titles = [m.group(1).strip() for m in _SECTION_RE.finditer(text)]
    if titles and not any(_INTRO_TITLE_RE.search(t) for t in titles):
        mechanisms.append(_mechanism(
            "a", "document opening",
            "no introduction beat: the paper opens into content with no section that "
            "teaches the subject before it is used",
            quote=titles[0][:80]))

    prose = _strip_math(text)

    for name, pat in _PROVENANCE_LEXICON:
        hit = pat.search(prose)
        if hit:
            mechanisms.append(_mechanism(
                "d", f"prose ({name})",
                "provenance narration: the prose reports how a number was obtained "
                "rather than using it",
                quote=hit.group(0)[:80]))

    seen_ledger: set[str] = set()
    for hit in _LEDGER_NAME_RE.finditer(prose):
        token = hit.group(1)
        if token in seen_ledger:
            continue
        seen_ledger.add(token)
        mechanisms.append(_mechanism(
            "d", f"prose ({token})",
            "ledger name in prose: a store quantity id is set to a number in the "
            "sentence line, a config file narrated aloud",
            quote=hit.group(0)[:80]))
        if len(seen_ledger) >= 4:              # a handful is enough to name the class
            break

    hedges = [name for name, pat in _HEDGING_LEXICON if pat.search(prose)]
    if len(hedges) >= _HEDGING_DENSITY_FLOOR:
        mechanisms.append(_mechanism(
            "d", "prose (hedging)",
            "per-number hedging: caveats are worn as a disclaimer on nearly every "
            f"claim ({', '.join(hedges)}); consolidate them into a limitations section"))

    return mechanisms


# ---------------------------------------------------------------------------
# 3. Package the read -- the reader prompt (no model call)
# ---------------------------------------------------------------------------

READER_INSTRUCTION = (
    "You are meeting a finished paper for the first time, as a stranger to it: you have "
    "only the pages in front of you -- no plan, no author's notes, no summary of what it "
    "was meant to be. Read the whole artefact front to back and answer one question: can "
    "a stranger read this as a self-contained object -- would a person read this, and "
    "would they be right to? Grade each item below and name every breach with where it "
    "sits and a short quote. Judge the pages in front of you, not what you happen to know "
    "about the field."
)

_RUBRIC = (
    "  (a) introduction: is there a real introduction that gives context, motivation, and "
    "a statement of the contribution, and teaches the subject before the paper prices it?\n"
    "  (b) definitions before use: is every symbol and term defined before it is used?\n"
    "  (c) arc: is there a thesis held across the paper, with sections that earn it, "
    "rather than audit rows in sequence?\n"
    "  (d) register: does the prose stay in a plain subject register, free of provenance "
    "narration (custody talk about how a number was obtained), config-style quantity names "
    "read aloud, and per-number hedging tics? Any such leak is a breach.\n"
    "  (e) figures and references: where the argument leans on a figure or a citation, is "
    "it present?"
)


def pack_reader_prompt(text: str, *, truncated: bool = False,
                       floor: Optional[list[dict[str, str]]] = None) -> dict[str, Any]:
    """Package the whole-object read into a reader prompt and payload -- it does not call
    a model. Mirrors the reader-suite package-and-parse shape: the artefact text is set
    behind a marker, the rubric and the verdict schema are stated, and ``truncated`` rides
    along so a partial read is never read as a whole one. Any mechanical-floor findings
    are named to the reader as a starting point, not a verdict.
    """
    floor_note = ""
    if floor:
        lines = "\n".join(f"  - [{m['class']}] {m['where']}: {m['finding']}" for m in floor)
        floor_note = ("\nA mechanical pass already flagged these; confirm or extend them, "
                      "and add anything it missed:\n" + lines + "\n")

    prompt = (
        f"{READER_INSTRUCTION}\n\n"
        f"grade:\n{_RUBRIC}\n"
        f"{floor_note}\n"
        'Return only JSON: {"verdict": "PASS" or "FAIL", "mechanisms": '
        '[{"class": one of a,b,c,d,e, "where": "<section or page>", "finding": '
        '"<one line>", "quote": "<short quote or empty>"}], "stranger_account": '
        '"<one paragraph, in your own words, of what the paper says>"}. '
        "A breach of any of (a)-(d) is a FAIL. Answer from the pages alone.\n\n"
        "=== the artefact (read only this) ===\n"
        f"{text}"
    )
    return {
        "organ": "readability_gate",
        "instruction": READER_INSTRUCTION,
        "rubric_classes": list(BREACH_CLASSES),
        "verdict_schema": ["verdict", "mechanisms", "stranger_account"],
        "model_hint": "a hold-out stranger reader; it never saw the paper being built",
        "floor": list(floor or []),
        "prompt": prompt,
        "truncated": bool(truncated),
    }


def compile_read_dispatch(prompt: str, *, model: str = GATE_MODEL,
                          effort: str = GATE_EFFORT) -> dict[str, Any]:
    """Stamp the reader dispatch with an explicit, clamped model -- the dispatch idiom
    carried by ``compile_dispatch``: the stamp rides the dispatch and is clamped to the
    ceiling (``schema.clamp_model``), so a reader is always opus-level or less and the
    model is never inherited from the orchestrator. Returns the descriptor the caller's
    reader-runner boundary consumes.
    """
    return {"organ": "readability_gate", "prompt": prompt,
            "model": schema.clamp_model(model), "effort": effort}


# ---------------------------------------------------------------------------
# 4. Parse the reply and settle the verdict -- deterministic, fail closed
# ---------------------------------------------------------------------------

def _coerce_json(raw: str) -> Any:
    """Pull a JSON body out of a possibly fenced or prosey reply (the reader-suite
    coercion shape). Returns the parsed object, or ``None`` when nothing parses."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = raw.find(opener), raw.rfind(closer)
        if 0 <= i < j:
            try:
                return json.loads(raw[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


def _normalise_mechanisms(raw: Any) -> list[dict[str, str]]:
    """Coerce a reader's ``mechanisms`` field into the standard shape, dropping anything
    that is not a dict. An unknown class is kept but does not force a FAIL (only a,b,c,d
    do), so a mis-classed finding is never lost."""
    out: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        cls = str(item.get("class", "")).strip().lower()[:1]
        out.append(_mechanism(
            cls if cls in BREACH_CLASSES else "?",
            str(item.get("where", "")).strip(),
            str(item.get("finding") or item.get("issue") or "").strip(),
            str(item.get("quote", "")).strip()))
    return out


def _unavailable(reason: str, detail: str, *, source: Optional[str] = None,
                 truncated: bool = False,
                 mechanisms: Optional[list[dict[str, str]]] = None) -> dict[str, Any]:
    return {"verdict": UNAVAILABLE, "reason": reason, "detail": detail,
            "mechanisms": list(mechanisms or []), "stranger_account": "",
            "source": source, "truncated": bool(truncated), "model": None}


def settle_verdict(parsed: Any, *, floor: Optional[list[dict[str, str]]] = None,
                   source: Optional[str] = None, truncated: bool = False,
                   model: Optional[str] = None) -> dict[str, Any]:
    """Settle the whole-object verdict deterministically -- the clean bit is computed
    here, not taken as the reader's claim (the reader-suite discipline). The mechanical
    floor and the reader's findings are merged; a breach of any of (a)-(d) from either
    side forces a FAIL. A PASS needs a reachable, parseable reader reply that says PASS,
    a non-empty stranger account, a whole (untruncated) read, and no fail-forcing breach.
    A truncated read that would otherwise pass cannot certify a whole-object PASS, so it
    is refused as ``UNAVAILABLE`` -- the whole object was never met.
    """
    floor = list(floor or [])
    if not isinstance(parsed, dict):
        return _unavailable(
            "unparseable_reply",
            "the reader reply did not parse into a verdict object",
            source=source, truncated=truncated, mechanisms=floor)

    reader_mechs = _normalise_mechanisms(parsed.get("mechanisms"))
    mechanisms = floor + reader_mechs
    stranger = str(parsed.get("stranger_account") or "").strip()
    reader_verdict = str(parsed.get("verdict") or "").strip().upper()

    has_fail_breach = any(m["class"] in FAIL_FORCING_CLASSES for m in mechanisms)

    if has_fail_breach or reader_verdict == FAIL:
        return {"verdict": FAIL, "reason": "breach", "detail": "",
                "mechanisms": mechanisms, "stranger_account": stranger,
                "source": source, "truncated": bool(truncated), "model": model}

    if reader_verdict != PASS:
        return _unavailable(
            "no_verdict",
            f"the reader named no PASS or FAIL verdict (got {reader_verdict!r})",
            source=source, truncated=truncated, mechanisms=mechanisms)

    if not stranger:
        return _unavailable(
            "no_account",
            "the reader returned no stranger account, so the read is incomplete",
            source=source, truncated=truncated, mechanisms=mechanisms)

    if truncated:
        return _unavailable(
            "truncated",
            "the read was truncated, so a whole-object PASS cannot be certified",
            source=source, truncated=True, mechanisms=mechanisms)

    return {"verdict": PASS, "reason": "", "detail": "",
            "mechanisms": mechanisms, "stranger_account": stranger,
            "source": source, "truncated": False, "model": model}


# ---------------------------------------------------------------------------
# 5. The gate -- read, floor, dispatch, settle
# ---------------------------------------------------------------------------

#: the reader-runner boundary the caller supplies: it takes the prompt and the stamped
#: model / effort and returns the reader's raw reply text. The orchestrator wires a
#: hold-out model runner here; a test stubs it. ``None`` means no reader is reachable.
DispatchFn = Callable[..., str]


def grade(manuscript_dir: Union[str, Path], *, dispatch: Optional[DispatchFn] = None,
          model: str = GATE_MODEL, effort: str = GATE_EFFORT,
          max_input_chars: int = DEFAULT_MAX_INPUT_CHARS) -> dict[str, Any]:
    """Grade the artefact's readability as a whole object. Reads the finished object,
    runs the mechanical floor, dispatches the whole-object read through the caller's
    reader boundary, and settles the verdict.

    Returns ``{verdict, mechanisms, stranger_account, source, truncated, model, ...}``.
    ``verdict`` is ``PASS`` / ``FAIL`` / ``UNAVAILABLE``. When there is no readable object,
    or no reader is reachable (``dispatch`` is ``None`` or it fails), the verdict is
    ``UNAVAILABLE`` -- the lock path treats that as blocking, so a paper whose readability
    could not be checked never locks. This function does not reach a model on its own; the
    model call is the ``dispatch`` boundary, which a test stubs.
    """
    art = read_whole_artefact(manuscript_dir, max_input_chars=max_input_chars)
    if not art["text"].strip():
        return _unavailable(
            "no_artefact",
            art.get("error") or "no compiled PDF and no tex to read",
            source=art["source"], truncated=art["truncated"])

    floor = structural_floor(art["text"], source=art["source"])
    packet = pack_reader_prompt(art["text"], truncated=art["truncated"], floor=floor)
    disp = compile_read_dispatch(packet["prompt"], model=model, effort=effort)

    if dispatch is None:
        return _unavailable(
            "no_model",
            "no reader model reachable (the dispatch boundary was not supplied)",
            source=art["source"], truncated=art["truncated"], mechanisms=floor)

    try:
        raw = dispatch(disp["prompt"], model=disp["model"], effort=disp["effort"])
    except Exception as exc:
        return _unavailable(
            "model_unreachable", f"the reader dispatch failed: {exc}",
            source=art["source"], truncated=art["truncated"], mechanisms=floor)

    if not raw or not str(raw).strip():
        return _unavailable(
            "empty_reply", "the reader returned no text",
            source=art["source"], truncated=art["truncated"], mechanisms=floor)

    parsed = _coerce_json(raw)
    return settle_verdict(parsed, floor=floor, source=art["source"],
                          truncated=art["truncated"], model=disp["model"])


# ---------------------------------------------------------------------------
# 6. The lock-tier surface -- does this verdict block, and why
# ---------------------------------------------------------------------------

def blocks_lock(verdict: dict[str, Any]) -> bool:
    """Whether this verdict blocks the candidate lock. Anything but a ``PASS`` blocks:
    a ``FAIL`` (a stranger cannot read it) and an ``UNAVAILABLE`` (the read could not be
    made) both hold the lock. Fail closed."""
    return (verdict or {}).get("verdict") != PASS


def refusal_reasons(verdict: dict[str, Any]) -> list[str]:
    """The refusal the lock path names when this verdict blocks, with the mechanisms
    named and located. Empty when the verdict is a ``PASS``."""
    v = (verdict or {}).get("verdict")
    if v == PASS:
        return []
    if v == UNAVAILABLE:
        reason = verdict.get("reason") or "unknown"
        detail = verdict.get("detail") or ""
        tail = f": {detail}" if detail else ""
        return [f"readability gate unavailable ({reason}){tail} -- "
                "a paper whose readability could not be checked never locks"]
    # a FAIL: name every mechanism
    named = [f"[{m.get('class', '?')}] {m.get('where', '?')}: {m.get('finding', '')}"
             for m in (verdict.get("mechanisms") or [])]
    if not named:
        named = ["a stranger could not read it front to back (no mechanism named)"]
    return ["readability gate fail -- a stranger cannot read this as a self-contained "
            "object:"] + named
