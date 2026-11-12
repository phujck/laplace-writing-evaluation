"""Deterministic index-time key expansion, question-side obligation splitting and question time windows.

Every rule here is a general text rule (no per-question patch, no gold input, no model call). Each key variant
replaces the turn's embedding key; the unit that is packed and read is unchanged (the raw turn).

KEY VARIANTS (doc side; `raw` is memory_benchmark.preprocess_text(role, content), the banked key):
  raw      "[role=<role>]\\n<content>"
  date     raw + "\\n[session date: 2023-05-30, Tuesday, May 30, 2023]"
  norm     raw + "\\n[mentions: <resolved dates>; <quantities as digits>]" when the turn has any (else raw)
  prev     "[role=<prev role>]\\n<prev content>\\n" + raw      (the loader's pair unit as the key)
  round    user turn: raw + "\\n[role=assistant]\\n<next content>"; assistant turn: "[role=user]\\n<prev>\\n" + raw
  dn       date + norm lines
  views    long turns (> 510 encoder tokens) also embedded as paragraph/sentence windows of <= 400 tokens; the
           turn's score is the max over its whole key and its views (L-D)
Resolution of relative dates is against the turn's own session date (the only anchor the turn has).
"""
from __future__ import annotations

import datetime as _dt
import re

MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")
MON_ABBR = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
NUMW = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
        "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "a couple of": 2,
        "a dozen": 12, "a": 1, "an": 1, "half a dozen": 6}
UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


def date_line(session_date: _dt.date) -> str:
    d = session_date
    return f"[session date: {d.isoformat()}, {WEEKDAYS[d.weekday()].title()}, {MONTHS[d.month - 1].title()} {d.day}, {d.year}]"


def _fmt(d: _dt.date) -> str:
    return f"{d.isoformat()} {WEEKDAYS[d.weekday()].title()} {MONTHS[d.month - 1].title()} {d.year}"


_NUMRE = r"(\d+|" + "|".join(sorted((k for k in NUMW if k not in ("a", "an")), key=len, reverse=True)) + r"|a|an)"


def _num(tok: str) -> int | None:
    tok = tok.lower()
    if tok.isdigit():
        return int(tok)
    return NUMW.get(tok)


def resolve_mentions(text: str, anchor: _dt.date) -> list[str]:
    """Dates (relative ones resolved against `anchor`) and word-form quantities, normalised. Order of appearance."""
    low = text.lower()
    found: list[tuple[int, str]] = []

    def add(pos, s):
        found.append((pos, s))

    for m in re.finditer(r"\b(today|tonight|this morning|this afternoon|this evening)\b", low):
        add(m.start(), f"{m.group(1)} = {_fmt(anchor)}")
    for m in re.finditer(r"\b(yesterday|last night)\b", low):
        add(m.start(), f"{m.group(1)} = {_fmt(anchor - _dt.timedelta(days=1))}")
    for m in re.finditer(r"\btomorrow\b", low):
        add(m.start(), f"tomorrow = {_fmt(anchor + _dt.timedelta(days=1))}")
    for m in re.finditer(r"\b" + _NUMRE + r" (day|week|month|year)s? ago\b", low):
        n = _num(m.group(1))
        if n:
            add(m.start(), f"{m.group(0)} = {_fmt(anchor - _dt.timedelta(days=n * UNIT_DAYS[m.group(2)]))}")
    for m in re.finditer(r"\b(last|this|next|on|past) (" + "|".join(WEEKDAYS) + r")\b", low):
        wd = WEEKDAYS.index(m.group(2))
        delta = (anchor.weekday() - wd) % 7
        if m.group(1) in ("last", "past", "on"):
            d = anchor - _dt.timedelta(days=delta or 7) if m.group(1) != "on" else anchor - _dt.timedelta(days=delta)
        elif m.group(1) == "next":
            d = anchor + _dt.timedelta(days=((wd - anchor.weekday()) % 7) or 7)
        else:
            d = anchor + _dt.timedelta(days=(wd - anchor.weekday()) % 7)
        add(m.start(), f"{m.group(0)} = {_fmt(d)}")
    for m in re.finditer(r"\b(last|this|next) (week|month|year)\b", low):
        unit, which = m.group(2), m.group(1)
        if unit == "year":
            y = anchor.year + {"last": -1, "this": 0, "next": 1}[which]
            add(m.start(), f"{m.group(0)} = {y}")
        elif unit == "month":
            mo = anchor.month + {"last": -1, "this": 0, "next": 1}[which]
            y = anchor.year + (mo - 1) // 12
            mo = (mo - 1) % 12 + 1
            add(m.start(), f"{m.group(0)} = {MONTHS[mo - 1].title()} {y}")
        else:
            mon = anchor - _dt.timedelta(days=anchor.weekday()) + _dt.timedelta(days=7 * {"last": -1, "this": 0, "next": 1}[which])
            add(m.start(), f"{m.group(0)} = week of {mon.isoformat()}")
    mon_re = "|".join(MONTHS) + "|" + "|".join(k + r"\.?" for k in MON_ABBR if k != "may")
    for m in re.finditer(r"\b(" + mon_re + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", low):
        mo = MON_ABBR[m.group(1)[:3]]
        day = int(m.group(2))
        y = int(m.group(3)) if m.group(3) else anchor.year
        try:
            d = _dt.date(y, mo, day)
        except ValueError:
            continue
        if not m.group(3) and d > anchor + _dt.timedelta(days=60):
            d = _dt.date(y - 1, mo, day) if not (mo == 2 and day == 29) else d
        add(m.start(), f"{m.group(0)} = {_fmt(d)}")
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)? of (" + "|".join(MONTHS) + r")\b", low):
        mo, day = MONTHS.index(m.group(2)) + 1, int(m.group(1))
        try:
            d = _dt.date(anchor.year, mo, day)
        except ValueError:
            continue
        add(m.start(), f"{m.group(0)} = {_fmt(d)}")
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", low):
        mo, day = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else anchor.year
        if y < 100:
            y += 2000
        try:
            d = _dt.date(y, mo, day)
        except ValueError:
            continue
        add(m.start(), f"{m.group(0)} = {_fmt(d)}")
    for m in re.finditer(r"\b(?:in|since|during|until|by|from) (" + "|".join(MONTHS) + r")\b(?!\s+\d)", low):
        mo = MONTHS.index(m.group(1)) + 1
        y = anchor.year if mo <= anchor.month else anchor.year - 1
        add(m.start(), f"{m.group(0)} = {MONTHS[mo - 1].title()} {y}")
    words = "|".join(sorted((k for k in NUMW if k not in ("a", "an")), key=len, reverse=True))
    for m in re.finditer(r"\b(" + words + r")\s+([a-z][a-z-]{2,})\b", low):
        n = NUMW[m.group(1)]
        add(m.start(), f"{n} {m.group(2)}")
    for m in re.finditer(r"\b(for|in|about|around|over|within) " + _NUMRE + r" (hour|day|week|month|year)s?\b", low):
        n = _num(m.group(2))
        if n:
            add(m.start(), f"duration {n} {m.group(3)}{'s' if n != 1 else ''}")
    found.sort(key=lambda x: x[0])
    out, seen = [], set()
    for _p, s in found:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def doc_keys(c, mb) -> dict[str, list[str]]:
    """All key variants for the turns of one case, in observation order."""
    from lm_core import parse_lm_date
    obs = c.obs
    raw = [mb.preprocess_text(o["role"], o["text"]) for o in obs]
    dates = [parse_lm_date(o["date"]) for o in obs]
    dl = [date_line(d) for d in dates]
    men = [resolve_mentions(o["text"], d) for o, d in zip(obs, dates)]
    nl = [("\n[mentions: " + "; ".join(m) + "]") if m else "" for m in men]
    prev, rnd = [], []
    for i, o in enumerate(obs):
        p = c.prev_local[i]
        prev.append((mb.preprocess_text(obs[p]["role"], obs[p]["text"]) + "\n" if p is not None else "") + raw[i])
        if o["role"] == "user":
            n = c.next_local[i]
            rnd.append(raw[i] + ("\n" + mb.preprocess_text(obs[n]["role"], obs[n]["text"]) if n is not None else ""))
        else:
            rnd.append(prev[i])
    return {"raw": raw, "date": [r + "\n" + d for r, d in zip(raw, dl)], "norm": [r + n for r, n in zip(raw, nl)],
            "dn": [r + "\n" + d + n for r, d, n in zip(raw, dl, nl)], "prev": prev, "round": rnd,
            "prev_dn": [p + "\n" + d + n for p, d, n in zip(prev, dl, nl)],
            "round_dn": [p + "\n" + d + n for p, d, n in zip(rnd, dl, nl)]}


def views(text: str, count_tokens, limit: int = 510, window: int = 400) -> list[str]:
    """Paragraph (newline) then sentence windows of <= `window` encoder tokens, for texts over `limit` tokens."""
    if count_tokens(text) <= limit:
        return []
    parts = [p for p in re.split(r"\n+", text) if p.strip()]
    pieces = []
    for p in parts:
        if count_tokens(p) <= window:
            pieces.append(p)
        else:
            pieces.extend(s for s in re.split(r"(?<=[.!?])\s+", p) if s.strip())
    out, cur = [], ""
    for s in pieces:
        cand = (cur + "\n" + s) if cur else s
        if cur and count_tokens(cand) > window:
            out.append(cur)
            cur = s
        else:
            cur = cand
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------------------------------------------------------ question side

_WH = r"^(which|what|how many|how much|how long|how old|how|when|where|who|whom|whose|did|do|does|is|are|was|were|have|has|can|could)\b"
_AUX = r"\b(did|do|does|have|has|had|am|is|are|was|were|i've|i'd|i)\b"
_STOP = {"the", "a", "an", "of", "to", "in", "on", "at", "for", "with", "my", "me", "i", "what", "which", "how", "many",
         "much", "long", "did", "do", "does", "have", "has", "had", "is", "was", "were", "are", "am", "total", "number",
         "first", "or", "and", "that", "this", "it", "from", "by", "about", "currently", "so", "far", "ago", "days",
         "since", "when", "been", "be", "there"}
_ORDER = r"\b(first|earlier|before|after|later|last|most recently|more|longer|sooner)\b"
_PREP = r"(?:from|in|at|to|with|of|for|about|between|on|during)"


def obligations(question: str) -> list[str]:
    """Deterministic split of a question into operand facets (the compiled obligations' text). Always includes the
    question. Rules, in order:
      comparison  '<stem>, (the) A or (the) B' with an order/comparison word in the stem -> stem-content + A, + B
      conjunction '<prep> A and (<prep>) B' or '<prep> A or B'                    -> the question with A, then with B
      verb list   'did I V1, V2, (and|or) V3 ...'                                  -> the question with each verb
      content     the question minus wh-words, auxiliaries and stop words (one facet)
    """
    q = question.strip().rstrip("?").strip()
    out = [question]
    m = re.match(r"^(.*?),\s*(?:the |my |a )?(.+?)\s+or\s+(?:the |my |a )?(.+)$", q, flags=re.I)
    if m and re.search(_ORDER, m.group(1), flags=re.I):
        stem = re.sub(_WH, "", m.group(1), flags=re.I)
        stem = re.sub(_ORDER, "", stem, flags=re.I)
        stem = re.sub(r"\s+", " ", stem).strip()
        out += [f"{stem} {m.group(2)}".strip(), f"{stem} {m.group(3)}".strip()]
    else:
        m3 = re.search(r"\b(?:did|have|do) i ((?:\w+, )+(?:(?:and|or) )?\w+)\b", q, flags=re.I)
        if m3:
            verbs = [v.strip() for v in re.split(r",|\band\b|\bor\b", m3.group(1)) if v.strip()]
            for v in verbs:
                out.append(q[:m3.start(1)] + v + q[m3.end(1):])
        else:
            for mc in re.finditer(r"\s+(and|or)\s+", q, flags=re.I):
                left = q[:mc.start()]
                preps = list(re.finditer(r"(?:\b" + _PREP + r"\b|,)\s*", left, flags=re.I))
                if not preps:
                    continue
                a_start = preps[-1].end()
                a = left[a_start:]
                rest = re.sub(r"^" + _PREP + r"\s+", "", q[mc.end():], flags=re.I)
                mb_ = re.match(r"(.+?)(?=\s+(?:" + _PREP + r"|this|last|so far|in the past)\b|$)", rest, flags=re.I)
                b = mb_.group(1) if mb_ else rest
                tail = rest[len(b):]
                if 0 < len(a.split()) <= 6 and 0 < len(b.split()) <= 6:
                    head = q[:a_start]
                    out += [f"{head}{a}{tail}".strip(), f"{head}{b}{tail}".strip()]
                break
    content = " ".join(w for w in re.findall(r"[\w'’-]+", q.lower()) if w not in _STOP)
    if content and content != q.lower():
        out.append(content)
    return list(dict.fromkeys(out))


# question time windows: index_gap.time_window's lexicon plus 'past (few|N) (days|weeks|months)', 'recently' is not a
# window. Returns (start, end) dates or None.

def question_window(question: str, question_date: str):
    from relational import index_gap as G
    from lm_core import parse_lm_date
    w = G.time_window(question, question_date)
    if w is not None:
        return _dt.date.fromisoformat(w["start"]), _dt.date.fromisoformat(w["end"])
    low = question.lower()
    q = parse_lm_date(question_date)
    m = re.search(r"\b(?:past|last) (few|couple of|" + _NUMRE[1:-1] + r") (day|week|month|year)s\b", low)
    if m:
        n = {"few": 3, "couple of": 2}.get(m.group(1)) or _num(m.group(1)) or 3
        return q - _dt.timedelta(days=n * UNIT_DAYS[m.group(2)]), q
    return None
