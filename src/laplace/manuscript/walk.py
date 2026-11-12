"""the redline walk (surface: ``/walk``) — the author's careful read of the frozen paper.

The clean-room ruling (DESIGN_2026-08-10_the-redline-walk.md §"The clean room"): the walk
is its OWN surface — ``walk.html`` + ``walk.mjs`` served here — with no shell chrome, no
journey nav, no mode machinery inherited from the artefact surface. Shared truth reaches it
through HTTP doors only (``/artefact/context``, ``/review/*``, ``/projection/*``); the front
end imports nothing but ``store.mjs``, the vendored libraries, and the fonts.

Pure handler module, the scanner-dispatch contract (mirrors ``artefact`` / ``review_surface``
/ ``projection_viewer``): the scanner owns the HTTP server and dispatches ``/walk*`` here via
:func:`handle`. This module NEVER starts a server, NEVER compiles, NEVER writes.

  * ``GET /walk``  — the one page (``walk.html``), with the ``?corpus=`` query PASSED THROUGH
                     into a single ``<meta name="walk:corpus">`` echo so a deep link opens on
                     the named project before the first fetch returns. The echo is the query,
                     not a resolution: the corpus AUTHORITY stays ``/artefact/context``
                     (``registry.project_context``), which names the corpus it resolved when
                     the query is empty. One producer, no surface-local project guessing.
  * ``GET /walk/doc?corpus=…``   — The block model (below): the content-faithful document,
                     built from the fragment sources + the build artifacts. The walk's canvas.
  * ``GET /walk/asset?corpus=…&file=…`` — one figure asset's BYTES, unrasterised (a figure
                     PDF is served as ``application/pdf`` for the client's pdf.js). Fenced
                     inside the manuscript directory.

The dual-faithful canvas (the contract, §"The dual-faithful canvas"): the walk's canvas is
the content-faithful source projection, not the PDF. ``/walk/doc`` is what makes that
possible — every rendered block carries the provenance every gesture addresses
(``{file, line_start, line_end}``), so the rewrite door's splice is deterministic and needs
no fuzzy quote match. The PDF stays the GEOMETRY FACE behind a door; it is not the working
canvas.

Everything here is a PURE READ. The walk's deposits and its rewrites ride
``/review/adjudicate`` (the ``comment``, ``rewrite`` and ``scope`` verbs); none of them
passes through this module.

The serving contract lives here too (:func:`gate_request`): with ``LAPLACE_WALK_ONLY`` set,
the scanner narrows to the walk and the doors the walk rides, and every other route answers
a plain 403 in words; with ``LAPLACE_WALK_TOKEN`` set alongside it, every gated request must
carry the token. It is ONE check, run at the top of the scanner's request handling, off by
default.
"""
from __future__ import annotations
from laplace.core.checkout import package_root

import json
import re
from bisect import bisect_right
from html import escape
from pathlib import Path
from typing import Any

from laplace.core import grammar as g
from laplace.core import identity_doors
from laplace.manuscript import manuscript_source

_HTML = package_root() / "web" / "walk.html"   # the page is the HTTP adapter's resource
_JSON = "application/json; charset=utf-8"

#: the single substitution point in ``walk.html`` — the corpus query, echoed.
_CORPUS_TOKEN = "__WALK_CORPUS__"

#: the fidelity sentence the surface states plainly, once (the register law). The walk's
#: canvas converges CONTENT; geometry is graded on the typeset face at finalize.
_FIDELITY = ("content-faithful: words, math, figures and order are the paper's own. "
             "Geometry — line breaks, page breaks, float placement — is deferred to the "
             "typeset face behind the PDF door.")


# ---------------------------------------------------------------------------
# small shared helpers
# ---------------------------------------------------------------------------

def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key, default)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else default
    return (v or default).strip()


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _repo_root() -> Path:
    from laplace.core.checkout import repo_root as rr   # the serving checkout's owner (the server module held the same object under an old name)
    return rr()


def page_bytes(corpus: str = "", *, template: bytes | None = None) -> bytes:
    """``walk.html`` with the corpus query echoed into its meta tag. The value is
    HTML-escaped (it lands inside an attribute), so a hostile ``?corpus=`` can only ever
    read back as text — never as markup."""
    html = template.decode("utf-8") if template is not None else _HTML.read_text(encoding="utf-8")
    return html.replace(_CORPUS_TOKEN, escape(corpus, quote=True)).encode("utf-8")


# ---------------------------------------------------------------------------
# THE SERVING CONTRACT — the walk-only gate
# ---------------------------------------------------------------------------
#
# One engine serves a dozen surfaces. When the walk is the only thing he wants reachable —
# a tunnel, a borrowed machine, a session where the desk and the pipeline have no business
# answering — this gate narrows the whole server to the walk and the doors the walk itself
# rides. It is OFF by default and changes nothing until an operator sets the env.
#
#   LAPLACE_WALK_ONLY=1     only the walk's own route prefixes answer; everything else
#                           gets a plain 403 that says what is being served instead.
#   LAPLACE_WALK_TOKEN=…    every gated request must also carry the token. Checked ONLY in
#                           walk-only mode: a token without the mode would be a half-locked
#                           door, which is worse than an open one because it reads as shut.
#
# THE GATE IS ONE CHECK, AT THE TOP. It runs in the scanner's ``parse_request`` — before
# any route branch, for every method — so no surface can be added later that quietly
# escapes it, and so the refusal costs nothing but the request line. The environment is
# read ONCE per process (:func:`gate_config`); a server does not re-read env per request.

WALK_ONLY_ENV = "LAPLACE_WALK_ONLY"
WALK_TOKEN_ENV = "LAPLACE_WALK_TOKEN"

#: the cookie a browser carries the token in after ONE authenticated request. A page fetches
#: its own module, its fonts, its doc model and its deposits; a token that only rides the
#: query would authorise the navigation and refuse every one of those, so the gated mode
#: would be unusable in the browser it exists to serve. Same-origin, HttpOnly, path-wide.
WALK_COOKIE = "laplace_walk"

#: what a gated scanner still answers: the walk's page and doors, the shared static the page
#: loads (its module, the vendored pdf.js/KaTeX, the fonts), the review doors its deposits
#: ride, the projection doors its geometry face reads, and the one context door that names
#: the corpus. Prefixes, matched on the PATH only.
_GATED_PREFIXES = ("/walk/", "/shared/", "/review/", "/projection/")
#: the exact paths, where a prefix would be too wide (``/artefact/context`` alone, not the
#: whole artefact surface) or too narrow (``/walk`` itself carries no trailing slash).
_GATED_EXACT = frozenset({"/walk", "/artefact/context", "/favicon.ico"})

#: the gate's env, read once. ``None`` until first use; :func:`gate_config` refreshes on
#: demand so a test can flip the mode without a new process.
_GATE: dict | None = None


def _truthy(v: str) -> bool:
    return (v or "").strip().lower() not in ("", "0", "false", "no", "off")


def gate_config(refresh: bool = False) -> dict:
    """The serving contract as this process will enforce it, read from the environment
    ONCE (``{"walk_only": bool, "token": str}``). ``refresh=True`` re-reads — the door a
    test uses to flip the mode, and the only way the cached read is ever revisited."""
    global _GATE
    if _GATE is None or refresh:
        import os
        _GATE = {"walk_only": _truthy(os.environ.get(WALK_ONLY_ENV, "")),
                 "token": (os.environ.get(WALK_TOKEN_ENV) or "").strip()}
    return dict(_GATE)


def gate_allows(path: str) -> bool:
    """Is ``path`` one of the routes a gated scanner serves? Path only — the query is
    never part of the decision, so no ``?`` trick widens the surface."""
    path = (path or "/").split("?", 1)[0].split("#", 1)[0]
    if path in _GATED_EXACT:
        return True
    return any(path.startswith(p) for p in _GATED_PREFIXES)


def _presented_token(query: dict, headers) -> str:
    """The token this request carries: ``?token=…``, an ``Authorization: Bearer …``, or the
    cookie a previously authenticated request set. First one present wins; absent is ``""``."""
    tok = _q1(query, "token")
    if tok:
        return tok
    get = getattr(headers, "get", None)
    if get is None:
        return ""
    auth = (get("Authorization") or "").strip()
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    for part in (get("Cookie") or "").split(";"):
        name, _, val = part.partition("=")
        if name.strip() == WALK_COOKIE:
            return val.strip()
    return ""


def gate_request(target: str, headers=None) -> dict:
    """The gate check. ``target`` is the raw request target (path and query as the
    request line carried it); ``headers`` is anything with ``.get(name)``.

    Returns ``{"refusal": (status, content_type, body) | None, "set_cookie": str}``.
    ``refusal`` present means the scanner answers it and handles nothing else; the words
    are plain text, because a refusal a curl reader cannot read is not a refusal.
    ``set_cookie`` is non-empty when this request authenticated by query or bearer and the
    scanner should hand the browser the cookie that carries it onward."""
    cfg = gate_config()
    if not cfg["walk_only"]:
        return {"refusal": None, "set_cookie": ""}
    from urllib.parse import parse_qs, urlparse

    u = urlparse(target or "/")
    if not gate_allows(u.path):
        body = (
            "403 — this engine is serving the redline walk only.\n\n"
            f"{u.path} is not one of the routes it answers in this mode. It serves "
            "/walk and the doors the walk itself rides: /walk/*, /shared/*, /review/*, "
            "/projection/*, /artefact/context, and the favicon. Nothing was read and "
            "nothing was written.\n\n"
            f"The mode is set by {WALK_ONLY_ENV} in the serving process's environment; "
            "unset it and the whole engine answers again.\n"
        )
        return {"refusal": (403, "text/plain; charset=utf-8", body.encode("utf-8")),
                "set_cookie": ""}
    token = cfg["token"]
    if not token:
        return {"refusal": None, "set_cookie": ""}
    import hmac

    q = parse_qs(u.query)
    presented = _presented_token(q, headers)
    if presented and hmac.compare_digest(presented, token):
        # the cookie is minted only where the token was proved by query or header; a
        # request that authenticated BY the cookie needs no fresh one.
        by_cookie = not (_q1(q, "token") or (
            getattr(headers, "get", lambda _n: "")("Authorization") or "").strip())
        return {"refusal": None,
                "set_cookie": "" if by_cookie else
                              f"{WALK_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict"}
    body = (
        "401 — this walk is token-gated and this request carried no matching token.\n\n"
        "Carry it as ?token=<value> on the URL or as an Authorization: Bearer <value> "
        "header. One authenticated request sets a same-origin cookie, so the page's own "
        "fetches carry it afterwards without the query. Nothing was read and nothing was "
        "written.\n\n"
        f"The token is set by {WALK_TOKEN_ENV} in the serving process's environment, and "
        f"is only enforced while {WALK_ONLY_ENV} is on.\n"
    )
    return {"refusal": (401, "text/plain; charset=utf-8", body.encode("utf-8")),
            "set_cookie": ""}


# ---------------------------------------------------------------------------
# TeX micro-scanners — brace/bracket matching, the one place it is written
# ---------------------------------------------------------------------------

def _brace_arg(s: str, i: int, *, literal: bool = False,
               require_closed: bool = False, known_macros=frozenset()) -> tuple[str, int]:
    """``s[i] == '{'`` -> ``(contents, index just past the matching '}')``. Nesting
    counted, ``\\{`` / ``\\}`` skipped as escapes. An unbalanced group returns what it
    has and the end of the string — a partial result, never a raise. Literal
    URL/path arguments retain backslashes as ordinary characters; require_closed
    refuses a partial group without changing the existing callers' fallback."""
    if i >= len(s) or s[i] != "{":
        return "", i
    depth = 0
    out: list[str] = []
    j = i
    n = len(s)
    while j < n:
        c = s[j]
        if not literal and c == "%":
            newline = s.find("\n", j)
            past = n if newline < 0 else newline
            if depth >= 1:
                out.append(s[j:past])
            j = past
            continue
        if not literal and c == "\\" and j + 1 < n:
            path = _path_literal(s, j, known_macros)
            if path is not None:
                _content, past = path
                if depth >= 1:
                    out.append(s[j:past])
                j = past
                continue
            if depth >= 1:
                out.append(s[j:j + 2])
            j += 2
            continue
        if c == "{":
            depth += 1
            if depth > 1:
                out.append(c)
        elif c == "}":
            depth -= 1
            if depth == 0:
                return "".join(out), j + 1
            out.append(c)
        else:
            if depth >= 1:
                out.append(c)
        j += 1
    return ("", i) if require_closed else ("".join(out), n)


def _opt_arg(s: str, i: int) -> tuple[str, int]:
    """A LaTeX optional argument at ``s[i]`` (``[...]``, brace-aware), or ``("", i)``."""
    if i >= len(s) or s[i] != "[":
        return "", i
    depth_b = 0
    depth_sq = 0
    j = i
    n = len(s)
    while j < n:
        c = s[j]
        if c == "\\" and j + 1 < n:
            j += 2
            continue
        if c == "{":
            depth_b += 1
        elif c == "}":
            depth_b -= 1
        elif depth_b == 0 and c == "[":
            depth_sq += 1
        elif depth_b == 0 and c == "]":
            depth_sq -= 1
            if depth_sq == 0:
                return s[i + 1:j], j + 1
        j += 1
    return "", i


def _demacro(s: str) -> str:
    """A TeX field flattened to plain words: escapes resolved, control words and accent
    commands dropped, braces removed, whitespace collapsed. Used only for the .bbl entry
    strings (a bibliography line the author READS, never a source the machine splices)."""
    for esc, ch in (("\\&", "&"), ("\\%", "%"), ("\\_", "_"),
                    ("\\$", "$"), ("\\#", "#")):
        s = s.replace(esc, ch)
    s = re.sub(r"\\[A-Za-z@]+\s*", "", s)          # control words
    s = re.sub(r"\\[^A-Za-z@\s]", "", s)           # accent commands (\"o, \'e, …)
    s = s.replace("~", " ").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# the preamble's macros — extracted mechanically, handed to KaTeX
# ---------------------------------------------------------------------------

#: ``\newcommand{\name}[n][default]{body}`` / ``\newcommand\name{body}`` / the renew and
#: provide variants. The body is brace-matched from the ``{`` this match ends on.
_NEWCMD_RE = re.compile(
    r"\\(?:new|renew|provide)command\s*\*?\s*"
    r"(?:\{\s*\\([A-Za-z@]+)\s*\}|\\([A-Za-z@]+))"
    r"\s*(?:\[\s*\d+\s*\])?\s*(?:\[[^\]]*\])?\s*\{")
_DECLAREOP_RE = re.compile(r"\\DeclareMathOperator\s*\*?\s*\{\s*\\([A-Za-z@]+)\s*\}\s*\{")
_DEF_RE = re.compile(r"\\def\s*\\([A-Za-z@]+)\s*\{")
_USEPACKAGE_RE = re.compile(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
_BEGIN_DOC_RE = re.compile(r"\\begin\s*\{document\}")


def _macros_from(text: str) -> dict[str, str]:
    """Every ``\\newcommand`` / ``\\DeclareMathOperator`` / ``\\def`` in ``text``, as the
    ``{"\\\\name": "expansion"}`` map KaTeX takes directly. Commented-out definitions are
    skipped (a ``%`` before the command on its line)."""
    out: dict[str, str] = {}
    for rx, wrap in ((_NEWCMD_RE, None),
                     (_DECLAREOP_RE, "\\operatorname{%s}"),
                     (_DEF_RE, None)):
        for m in rx.finditer(text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            if "%" in text[line_start:m.start()].replace("\\%", ""):
                continue                              # the definition is commented out
            name = next((g for g in m.groups() if g), "")
            if not name:
                continue
            body, _ = _brace_arg(text, m.end() - 1)
            out["\\" + name] = (wrap % body) if wrap else body
    return out


def preamble_macros(root_tex: Path) -> dict[str, str]:
    """The macros a KaTeX render of this paper needs: the root's preamble, plus every
    ``\\usepackage``d style file that lives BESIDE the root (a project's own ``.sty`` is
    part of its preamble; the distribution's packages are not ours to expand)."""
    try:
        text = root_tex.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    m = _BEGIN_DOC_RE.search(text)
    preamble = text[:m.start()] if m else text
    out = _macros_from(preamble)
    for mm in _USEPACKAGE_RE.finditer(preamble):
        for name in (n.strip() for n in mm.group(1).split(",")):
            sty = root_tex.parent / (name + ".sty")
            if name and sty.is_file():
                try:
                    out.update(_macros_from(sty.read_text(encoding="utf-8",
                                                          errors="replace")))
                except OSError:
                    continue
    return out


# ---------------------------------------------------------------------------
# the built artifacts — citations from the .bbl, cross-refs from the .aux
# ---------------------------------------------------------------------------

_BBL_FIELD_ORDER = ("author", "title", "booktitle", "journal", "volume",
                    "pages", "publisher", "year", "eprint")


def parse_bbl(text: str) -> dict[str, dict[str, Any]]:
    """The built bibliography, keyed by cite key: ``{key: {num, entry, ...}}``.

    ``num`` is the bibitem's ordinal — the number the built PDF prints, because a numeric
    style lists in citation order. ``entry`` is the bibitem's ``\\bibinfo`` fields flattened
    to one readable line; a bibitem carrying no ``\\bibinfo`` falls back to its whole body
    de-macro'd, so an entry is never silently empty."""
    out: dict[str, dict[str, Any]] = {}
    n = len(text)
    marks: list[tuple[str, int]] = []        # (key, body start index)
    i = 0
    while True:
        i = text.find("\\bibitem", i)
        if i < 0:
            break
        j = i + len("\\bibitem")
        while j < n and text[j] in " \t\n":
            j += 1
        _, j = _opt_arg(text, j)
        while j < n and text[j] in " \t\n":
            j += 1
        if j < n and text[j] == "{":
            key, j = _brace_arg(text, j)
            key = key.strip()
            if key:
                marks.append((key, j))
        i = max(j, i + 1)
    for idx, (key, start) in enumerate(marks):
        end = marks[idx + 1][1] if idx + 1 < len(marks) else n
        body = text[start:end]
        stop = body.find("\\bibitem")
        if stop >= 0:
            body = body[:stop]
        fields: dict[str, list[str]] = {}
        k = 0
        while True:
            k = body.find("\\bibinfo", k)
            if k < 0:
                break
            k += len("\\bibinfo")
            while k < len(body) and body[k] in " \t\n":
                k += 1
            fname, k = _brace_arg(body, k)
            while k < len(body) and body[k] in " \t\n":
                k += 1
            fval, k = _brace_arg(body, k)
            fname = _demacro(fname)
            fval = _demacro(fval)
            if fname and fval:
                fields.setdefault(fname, []).append(fval)
        parts: list[str] = []
        authors = fields.get("author") or fields.get("editor") or []
        if authors:
            parts.append(", ".join(authors))
        for f in _BBL_FIELD_ORDER:
            if f in ("author",):
                continue
            for v in fields.get(f, []):
                parts.append(v)
        entry = ", ".join(p for p in parts if p) or _demacro(body)
        out[key] = {"num": idx + 1, "entry": entry,
                    "fields": {k2: v for k2, v in fields.items()}}
    return out


_BIB_RESOURCE_RE = re.compile(r"\\(?:bibliography|addbibresource)\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}")
_BIB_ENTRY_RE = re.compile(r"@\s*[A-Za-z]+\s*\{\s*([^,\s]+)\s*,", re.I)
_BIBITEM_RE = re.compile(r"\\bibitem\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}")
_THEBIB_RE = re.compile(r"\\begin\s*\{thebibliography\}(?:\s*\{[^}]*\})?(.*?)"
                        r"\\end\s*\{thebibliography\}", re.S)


def _bib_field(body: str, name: str) -> str:
    match = re.search(r"(?:^|,)\s*" + re.escape(name) + r"\s*=\s*", body, re.I)
    if match is None:
        return ""
    start = match.end()
    if start < len(body) and body[start] == "{":
        value, _ = _brace_arg(body, start)
        return _demacro(value)
    if start < len(body) and body[start] == '"':
        end = body.find('"', start + 1)
        return _demacro(body[start + 1:end if end >= 0 else len(body)])
    end = body.find(",", start)
    return _demacro(body[start:end if end >= 0 else len(body)])


def _bib_targets(text: str, source: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    marks = list(_BIB_ENTRY_RE.finditer(text))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        body = text[mark.end():end]
        rows.append({"key": mark.group(1).strip(), "title": _bib_field(body, "title"),
                     "year": _bib_field(body, "year"), "source": source})
    return rows


def _inline_bib_targets(text: str, source: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for bibliography in _THEBIB_RE.findall(text):
        marks = list(_BIBITEM_RE.finditer(bibliography))
        for index, mark in enumerate(marks):
            end = marks[index + 1].start() if index + 1 < len(marks) else len(bibliography)
            body = _demacro(bibliography[mark.end():end])
            year = next(iter(re.findall(r"\b(?:19|20)\d{2}\b", body)), "")
            rows.append({"key": mark.group(1).strip(), "title": body, "year": year,
                         "source": source})
    return rows


def inline_citations(source_tree: dict, bib_numbers: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Citation records from authored ``thebibliography`` blocks, never a guessed number."""
    rows: dict[str, dict[str, Any]] = {}
    for source in source_tree.get("sources", []):
        text = str(source.get("text") or "")
        for bibliography in _THEBIB_RE.findall(text):
            for key, value in parse_bbl(bibliography).items():
                row = {"entry": value.get("entry") or "", "fields": value.get("fields") or {}}
                if key in bib_numbers:
                    row["num"] = bib_numbers[key]
                rows.setdefault(key, row)
    return rows


def citation_targets(root_tex: Path, manuscript: Path, source_tree: dict,
                     citations: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Pre-build citation picker entries from local bibliography sources only."""
    ordered: dict[str, dict[str, str]] = {}

    def add(row: dict[str, str]) -> None:
        key = str(row.get("key") or "").strip()
        if not key:
            return
        prior = ordered.get(key, {})
        ordered[key] = {"key": key,
                        "title": str(row.get("title") or prior.get("title") or ""),
                        "year": str(row.get("year") or prior.get("year") or ""),
                        "source": str(prior.get("source") or row.get("source") or "")}

    root_text = root_tex.read_text(encoding="utf-8", errors="replace")
    for match in _BIB_RESOURCE_RE.finditer(root_text):
        for raw in match.group(1).split(","):
            name = raw.strip()
            if not name:
                continue
            path = (root_tex.parent / name).with_suffix(Path(name).suffix or ".bib")
            if path.is_file():
                for row in _bib_targets(path.read_text(encoding="utf-8", errors="replace"),
                                        path.name):
                    add(row)
    for source in source_tree.get("sources", []):
        text = str(source.get("text") or "")
        for row in _inline_bib_targets(text, str(source.get("file") or "inline")):
            add(row)
    associations = manuscript / "references.json"
    try:
        linked = json.loads(associations.read_text(encoding="utf-8")).get("associations", [])
    except (OSError, ValueError, AttributeError):
        linked = []
    for row in linked if isinstance(linked, list) else []:
        if not isinstance(row, dict):
            continue
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        add({"key": str(row.get("citekey") or ""), "title": str(metadata.get("title") or ""),
             "year": str(metadata.get("year") or ""), "source": "association"})
    for key, row in citations.items():
        add({"key": key, "title": str(row.get("entry") or ""), "year": "", "source": "built"})
    return list(ordered.values())


#: ``\newlabel{name}{{printed}{page}{…}{anchor}{…}}`` — the printed number is the first
#: inner group, the page the second. Labels carrying ``@`` are a package's private
#: bookkeeping (cleveref's ``@cref`` twins), never something the paper prints.
_NEWLABEL_RE = re.compile(r"\\newlabel\s*\{([^}]*)\}\s*\{\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_BIBCITE_RE = re.compile(r"\\bibcite\s*\{([^}]*)\}\s*\{([^}]*)\}")


def parse_aux(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """The cross-reference numbers the last build assigned: ``({label: number},
    {label: page})``. Both come from the SAME ``\\newlabel`` line, so a label present in
    one map is present in the other."""
    nums: dict[str, str] = {}
    pages: dict[str, str] = {}
    for m in _NEWLABEL_RE.finditer(text):
        label = m.group(1).strip()
        if not label or "@" in label:
            continue
        nums[label] = m.group(2).strip()
        pages[label] = m.group(3).strip()
    return nums, pages


def parse_aux_citations(text: str) -> dict[str, str]:
    """Numbers assigned by this exact aux to inline or BibTeX citation keys."""
    return {match.group(1).strip(): match.group(2).strip()
            for match in _BIBCITE_RE.finditer(text) if match.group(1).strip()}


# ---------------------------------------------------------------------------
# WO-20260810-walk-bbl-aux-artifacts: main.bbl/main.aux fallback resolution.
# doc() used to read these ONLY from the resolved manuscript dir (``md``). Four
# of five corpora walked showed empty citations/refs tables: falqon + eigenengine
# have no built .bbl/.aux ANYWHERE (never bibtex-compiled in place — honestly
# absent, no fallback fixes that), but subset-sum-itqde DOES have them, just not
# at ``md`` — its main.aux lives at the registry's ``tex_root`` (the corpus's
# actual compile root, foreign to the deposited ``manuscript_dir`` — see
# registry.Project's tex_root/manuscript_dir split) and its main.bbl lives under
# a versioned snapshot (``versions/<name>/whitepaper/``). Both are already-built
# artifacts on disk; no bibtex pass is run here, only a wider, cheap read.
# ---------------------------------------------------------------------------

def _bib_artifact_candidates(md: Path, corpus: str, filename: str,
                             root_tex: Path | None = None) -> list[Path]:
    """Candidate paths for a built bibliography artifact (``main.bbl`` /
    ``main.aux``), in resolution order: the resolved manuscript dir itself first
    (unchanged precedence), then the registry's ``tex_root`` for this corpus (the
    actual tex compile root, which can differ from ``md`` — the foreign-tex-tree
    split), then every versioned snapshot under the registry's ``versions_dir``
    that carries the file (``versions/*/whitepaper/<filename>``), newest first.
    Registry lookup is best-effort: an unknown corpus or a registry read problem
    just narrows this to the one candidate ``doc()`` always had."""
    seen: set[Path] = set()
    out: list[Path] = []

    def add(p: Path | None) -> None:
        if p is not None and p.resolve() not in seen:
            seen.add(p.resolve())
            out.append(p)

    # The selected root need not be called main.tex.  Prefer its own build
    # artifact (Synthetics.tex -> Synthetics.aux) before legacy main.* fallbacks.
    if root_tex is not None:
        add(root_tex.with_suffix(Path(filename).suffix))
    add(md / filename)
    if not corpus:
        return out
    try:
        from laplace.pipeline import registry
        proj = registry.resolve(corpus)
    except Exception:  # noqa: BLE001 - registry lookup here is best-effort
        proj = None
    if proj is None:
        return out
    root = _repo_root().resolve()
    if proj.tex_root:
        add(root / proj.tex_root / filename)
    versions_dir = getattr(proj, "versions_dir", "") or ""
    if versions_dir:
        vdir = root / versions_dir
        if vdir.is_dir():
            matches = sorted(
                (p for p in vdir.glob(f"*/whitepaper/{filename}") if p.is_file()),
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
            for m in matches:
                add(m)
    return out


def _artifact_has_payload(path: Path, filename: str) -> bool:
    """Whether a built aux/bbl carries the records its consumer needs.

    A zero-label ``main.aux`` and a bib-less ``main.bbl`` are legitimate compile
    stubs, but a historical snapshot with more bytes is not automatically a better
    match for the current manuscript. Selection follows current-root precedence;
    this predicate only decides whether that candidate is usable before falling
    back to the other registered roots.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if filename == "main.aux":
        return "\\newlabel" in text
    if filename == "main.bbl":
        return "\\bibitem" in text
    return bool(text.strip())


def _resolve_bib_artifact(md: Path, corpus: str, filename: str,
                          root_tex: Path | None = None) -> Path | None:
    """Return the first usable candidate in current-root precedence order.

    The old size-based rule could select a larger historical snapshot (SSG's
    2026-07-03 aux is larger than the current whitepaper aux), pairing old labels
    such as ``sec:S1`` with current fragments labelled ``sec:N1``. Prefer the
    current root, then the registered tex root, then historical snapshots; only
    skip candidates that are empty compile stubs.
    """
    candidates = _bib_artifact_candidates(md, corpus, filename, root_tex)
    for candidate in candidates:
        if candidate.is_file() and _artifact_has_payload(candidate, filename):
            return candidate
    return next((candidate for candidate in candidates if candidate.is_file()), None)


# ---------------------------------------------------------------------------
# the piece tokenizer — a paragraph's source as renderable content
# ---------------------------------------------------------------------------

_CITE_CMDS = frozenset({"cite", "citep", "citet", "citealp", "citealt",
                        "citeauthor", "citenum", "onlinecite", "textcite"})
_REF_CMDS = frozenset({"ref", "eqref", "autoref", "cref", "Cref", "pageref",
                       "nameref"})
_EMPH_CMDS = frozenset({"emph", "textit", "textsl"})
_BOLD_CMDS = frozenset({"textbf"})
_CODE_CMDS = frozenset({"texttt"})
_PLAIN_CMDS = frozenset({"text", "textrm", "textnormal", "mbox", "textsc", "textls"})
#: commands whose whole call renders nothing on the page (bookkeeping the block records
#: separately). Dropping them is not "silently dropping content" — they ARE not content.
_SILENT_CMDS = frozenset({"label", "index", "nonumber", "noindent", "centering",
                          "raggedright", "raggedleft", "strut",
                          "protect", "linebreak", "newpage", "clearpage", "small",
                          "footnotesize", "ttfamily", "itshape", "begingroup", "endgroup"})
_PRESENTATION_ARGS = {"color": 1, "hypersetup": 1, "thispagestyle": 1, "pagestyle": 1,
                      "vspace": 1, "hspace": 1, "fontsize": 2, "rule": 2}
_PRESENTATION_SWITCHES = frozenset({"tiny", "scriptsize", "normalsize", "large", "Large",
    "LARGE", "huge", "Huge", "sffamily", "rmfamily", "normalfont", "bfseries", "mdseries",
    "upshape", "slshape", "scshape", "selectfont", "vfill", "hfill"})
_TEXT_ESCAPES = frozenset("%&_$#{}")

_CTRL_WORD_RE = re.compile(r"\\([A-Za-z@]+)\*?")


def _find_math_close(s: str, i: int, close: str) -> int:
    """The index of the next unescaped ``close`` at or after ``i`` (len(s) if none)."""
    n = len(s)
    while i < n:
        if s.startswith(close, i):
            return i
        if s[i] == "\\":
            i += 2
            continue
        i += 1
    return n


def _text_norm(s: str) -> str:
    """A prose run as it READS: TeX's ties and dashes and quotes resolved, source line
    breaks collapsed to the single space TeX itself sets. Never applied inside math."""
    s = s.replace("~", "\u00a0")
    s = s.replace("---", "\u2014").replace("--", "\u2013")
    s = s.replace("``", "\u201c").replace("''", "\u201d")
    return re.sub(r"[ \t\r\n]+", " ", s)


def _literal_path_arg(tex: str, start: int) -> tuple[str, int] | None:
    """Standard url.sty path argument; no prose/macro/escape interpretation."""
    if start >= len(tex):
        return None
    if tex[start] == "{":
        content, end = _brace_arg(tex, start, literal=True, require_closed=True)
        return (content, end) if end > start else None
    delimiter = tex[start]
    if delimiter.isspace() or delimiter == "}":
        return None
    end = tex.find(delimiter, start + 1)
    return (tex[start + 1:end], end + 1) if end >= 0 else None


def _path_literal(tex: str, start: int, known_macros=frozenset()) -> tuple[str, int] | None:
    """The same standard literal boundary for inline and structural readers."""
    cursor = start - 1
    while cursor >= 0 and tex[cursor] == "\\":
        cursor -= 1
    if (start - cursor - 1) % 2 or "\\path" in known_macros:
        return None
    command = _CTRL_WORD_RE.match(tex, start)
    if not command or command.group(1) != "path" or command.group().endswith("*"):
        return None
    cursor = command.end()
    while cursor < len(tex) and tex[cursor] in " \t\r\n":
        cursor += 1
    return _literal_path_arg(tex, cursor)


def _path_source_end(tex: str, start: int) -> int:
    """Available exact source for an unsupported path, without guessed structure."""
    command = _CTRL_WORD_RE.match(tex, start)
    cursor = command.end() if command else start
    while cursor < len(tex) and tex[cursor] in " \t\r\n":
        cursor += 1
    if cursor < len(tex) and tex[cursor] == "{":
        _partial, end = _brace_arg(tex, cursor, literal=True)
        return end
    return len(tex)


def _literal_tex_url(value: str) -> str | None:
    """Decode supported URL literal escapes without evaluating TeX macros.

    URI policy remains the shared reader's job. An unresolved macro cannot be
    silently treated as a browser path separator or a resolved owner URI.
    """
    decoded=re.sub(r'\\([&%_#$])',lambda match:match.group(1),value)
    return None if '\\' in decoded else decoded


def tex_pieces(tex: str, known_macros: frozenset[str] = frozenset(),
               base: int = 0) -> list[dict]:
    """One paragraph's source tokenized into renderable pieces.

    ``[{t:"text",s} | {t:"math",s,display} | {t:"cite",keys} | {t:"ref",label,cmd} |
    {t:"emph",s} | {t:"bold",s} | {t:"code",s} | {t:"break"} | {t:"macro",name,s,args,known}]``

    A macro the tokenizer does not type reads back as a ``macro`` piece carrying its
    VERBATIM source and ``known`` (true when the preamble defines it) — the surface marks
    it visibly rather than dropping it, which is the honesty this canvas turns on.

    The piece source offsets (GAP-20260810-piece-source-offsets). Every piece carries
    ``{o_start, o_end}`` — half-open character offsets into the string it was tokenized
    from, shifted by ``base``. THE INVARIANT, asserted in the fences:
    ``tex[o_start:o_end]`` IS that piece's source, for every piece, with the pieces in
    document order and non-overlapping. The tokenizer knows where it is when it emits;
    recording it costs nothing and makes the client's rendered-char → source-char map
    PIECEWISE-EXACT instead of prose-only — so a selection adjacent to, or spanning
    across, inline math or a citation splices deterministically instead of falling to
    the pending path.

    ``base`` exists for callers tokenizing a SLICE of a larger block (a list item), so
    the offsets a piece carries still address that block's own ``tex``."""
    pieces: list[dict] = []
    buf: list[str] = []
    buf_at = 0
    n = len(tex)

    def push(ch: str, at: int) -> None:
        nonlocal buf_at
        if not buf:
            buf_at = at
        buf.append(ch)

    def flush(end: int) -> None:
        if buf:
            s = _text_norm("".join(buf))
            if s:
                pieces.append({"t": "text", "s": s,
                               "o_start": base + buf_at, "o_end": base + end})
            buf.clear()

    i = 0
    while i < n:
        c = tex[i]
        if c == "{":
            inner, end = _brace_arg(tex, i, known_macros=known_macros)
            if end > i and end <= n and tex[end - 1:end] == "}":
                flush(i)
                children = tex_pieces(inner, known_macros, base=base + i + 1)
                pieces.append({"t": "group", "pieces": children,
                               "o_start": base + i, "o_end": base + end})
                i = end
                continue
        # Structural environments inside a theorem/proof are still structure.
        # Keep the original outer span; recursively typed contents carry offsets
        # into that same source, never offsets into a rewritten TeX string.
        if tex.startswith("\\begin", i):
            opening = re.match(r"\\begin\s*\{([^}]+)\}", tex[i:])
            env = opening.group(1) if opening else ""
            if env in _MATH_ENVS | _LIST_ENVS | {"algorithmic"}:
                body = _environment_body(tex[i:], env, known_macros=known_macros)
                if body:
                    inner, lo, hi = body
                    closing = re.match(r"\\end\s*\{" + re.escape(env) + r"\}", tex[i + hi:])
                    end = i + hi + closing.end()
                    flush(i)
                    piece = {"o_start": base + i, "o_end": base + end}
                    if env in _MATH_ENVS:
                        math, equation_labels = _equation_math(inner)
                        piece.update(t="math", s=math, display=True, env=env,
                                     labels=[row['label'] for row in equation_labels],
                                     equation_labels=equation_labels)
                    elif env in _LIST_ENVS:
                        lead = len(inner) - len(inner.lstrip())
                        _options, past = _opt_arg(inner, lead)
                        if past != lead:
                            inner, lo = inner[past:], lo + past
                        piece.update(t="list", env=env, ordered=env == "enumerate",
                                     items=list_items(inner, known_macros, base=base + i + lo))
                    else:
                        lead = len(inner) - len(inner.lstrip())
                        _options, past = _opt_arg(inner, lead)
                        if past != lead:
                            inner, lo = inner[past:], lo + past
                        piece.update(t="algorithm", pieces=algorithm_pieces(inner, known_macros, base + i + lo))
                    pieces.append(piece)
                    i = end
                    continue
        if c == "%":                                   # a comment runs to end of line
            j = tex.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c == "$":
            display = tex.startswith("$$", i)
            close = "$$" if display else "$"
            j = _find_math_close(tex, i + len(close), close)
            flush(i)
            end = min(j + len(close), n)
            pieces.append({"t": "math", "s": tex[i + len(close):j], "display": display,
                           "o_start": base + i, "o_end": base + end})
            i = end
            continue
        if c == "\\":
            nxt = tex[i + 1:i + 2]
            if nxt in ("(", "["):
                close = "\\)" if nxt == "(" else "\\]"
                j = tex.find(close, i + 2)
                j = n if j < 0 else j
                flush(i)
                end = min(j + 2, n)
                pieces.append({"t": "math", "s": tex[i + 2:j], "display": nxt == "[",
                               "o_start": base + i, "o_end": base + end})
                i = end
                continue
            if nxt in _TEXT_ESCAPES:
                push(nxt, i)
                i += 2
                continue
            if nxt == "\\":
                flush(i)
                pieces.append({"t": "break",
                               "o_start": base + i, "o_end": base + i + 2})
                i += 2
                continue
            m = _CTRL_WORD_RE.match(tex, i)
            if m is None:
                push(c, i)
                i += 1
                continue
            name = m.group(1)
            k = m.end()
            while k < n and tex[k] in " \t\n":         # a control word eats its spaces
                k += 1
            if name == "path":
                # Unlike texttt, path changes catcodes: %/_/backslash/math-like
                # characters are literal. Reuse the existing code atom, never
                # recursively tokenize its body or infer a clickable source link.
                literal = _path_literal(tex, i, known_macros)
                flush(i)
                if literal is not None:
                    content, end = literal
                    pieces.append({"t": "code", "s": content, "command": "path", "literal": True,
                                   "o_start": base + i, "o_end": base + end})
                else:
                    end = _path_source_end(tex, i)
                    pieces.append({"t": "raw", "s": tex[i:end], "command": "path",
                                   "reason": "Unsupported, redefined or unbalanced inline path; inspect its exact source.",
                                   "o_start": base + i, "o_end": base + end})
                i = end
                continue
            options: list[str] = []
            while k < n and tex[k] == "[" and len(options) < 3:
                option, past = _opt_arg(tex, k)
                if past == k:
                    break
                options.append(option)
                k = past
                while k < n and tex[k] in " \t\n":
                    k += 1
            if name in _PRESENTATION_ARGS or name in _PRESENTATION_SWITCHES:
                cursor, valid = k, True
                for _ in range(_PRESENTATION_ARGS.get(name, 0)):
                    while cursor < n and tex[cursor].isspace(): cursor += 1
                    if cursor >= n or tex[cursor] != "{": valid = False; break
                    _, past = _brace_arg(tex, cursor)
                    if past <= cursor or tex[past - 1:past] != "}": valid = False; break
                    cursor = past
                if valid:
                    flush(i)
                    pieces.append({"t": "presentation", "name": name,
                                   "o_start": base + i, "o_end": base + cursor})
                    i = cursor
                    continue
            if name == "parbox" and k < n and tex[k] == "{":
                try:
                    width, after_width = _brace_arg(tex, k)
                    cursor = after_width
                    while cursor < n and tex[cursor] in " \t\n":
                        cursor += 1
                    if cursor < n and tex[cursor] == "{":
                        body, after_body = _brace_arg(tex, cursor)
                        flush(i)
                        pieces.append({"t": "parbox", "geometry": {
                                           "position": options[0] if options else "",
                                           "height": options[1] if len(options) > 1 else "",
                                           "inner_position": options[2] if len(options) > 2 else "",
                                           "width": width},
                                       "pieces": tex_pieces(body, known_macros,
                                                            base=base + cursor + 1),
                                       "o_start": base + i, "o_end": base + after_body})
                        i = after_body
                        continue
                except (ValueError, IndexError):
                    pass
            if name == "newblock":
                flush(i)
                pieces.append({"t":"symbol", "s":" ", "o_start":base+i, "o_end":base+k})
                i = k
                continue
            if name in {"ldots", "dots", "textellipsis"}:
                flush(i)
                pieces.append({"t": "symbol", "s": "…", "o_start": base + i, "o_end": base + k})
                i = k
                continue
            if name in {"medskip", "smallskip", "bigskip"}:
                flush(i)
                pieces.append({"t": "break", "size": name,
                               "o_start": base + i, "o_end": base + k})
                i = k
                continue
            if name == "S":
                flush(i)
                pieces.append({"t": "symbol", "s": "§",
                               "o_start": base + i, "o_end": base + k})
                i = k
                continue
            if name in {"newline", "par"}:
                flush(i)
                pieces.append({"t": "break", "o_start": base + i, "o_end": base + k})
                i = k
                continue
            # A declared zero-argument description-item macro (e.g. \says)
            # gets its label from the manuscript's actual macro definition.
            expansion = known_macros.get("\\" + name) if isinstance(known_macros, dict) else None
            if isinstance(expansion, str) and expansion.startswith("\\item[") and "#" not in expansion:
                label, past = _opt_arg(expansion, len("\\item"))
                if past == len(expansion):
                    flush(i)
                    pieces.append({"t": "semantic-label", "pieces": tex_pieces(label),
                                   "o_start": base + i, "o_end": base + k})
                    i = k
                    continue
            if name in _SILENT_CMDS:
                if name in {"label", "index"} and k < n and tex[k] == "{":
                    _, k = _brace_arg(tex, k)
                i = k
                continue
            if name in {"hspace", "phantom"}:
                if k < n and tex[k] == "{": _, k = _brace_arg(tex, k)
                i = k; continue
            if name == "quad":
                push(" ", i); i = k; continue
            if k < n and tex[k] == "{":
                arg, k2 = _brace_arg(tex, k, known_macros=known_macros)
                if name == "num" and expansion == r"\textcolor{red}{\texttt{[#1]}}":
                    flush(i)
                    pieces.append({"t": "placeholder", "s": arg, "key": arg,
                                   "reason": "The authored source still declares this value unresolved.",
                                   "o_start": base + i, "o_end": base + k2})
                    i = k2
                    continue
                if (name == "claim" and isinstance(expansion, str)
                        and re.fullmatch(
                            r"\\textsuperscript\{(?:\[C#1\]|"
                            r"\\textcolor\{[^{}]+\}\{\[C#1\]\})\}",
                            expansion)):
                    flush(i)
                    pieces.append({"t": "provenance-label", "s": "[C" + arg + "]",
                                   "provenance_kind": "declared-claim-tag", "value": arg,
                                   "declared_expansion": expansion,
                                   "o_start": base + i, "o_end": base + k2})
                    i = k2
                    continue
                if name in _CITE_CMDS:
                    flush(i)
                    pieces.append({"t": "cite",
                                   "keys": [t.strip() for t in arg.split(",") if t.strip()],
                                   "o_start": base + i, "o_end": base + k2})
                    i = k2
                    continue
                if name in {"href", "textcolor"}:
                    start = k2
                    while start < n and tex[start].isspace(): start += 1
                    if start < n and tex[start] == "{":
                        body, end = _brace_arg(tex, start)
                        if end > start and tex[end - 1:end] == "}":
                            nested = tex_pieces(body, known_macros, base=base + start + 1)
                            flush(i)
                            pieces.append({"t": "href" if name == "href" else "group",
                                           "url": _literal_tex_url(arg) if name == "href" else None,
                                           **({'url_source':arg} if name=='href' else {}),
                                           "s": _flatten_pieces(nested), "pieces": nested,
                                           "o_start": base + i, "o_end": base + end})
                            i = end
                            continue
                if name == "url":
                    flush(i)
                    pieces.append({"t": "url", "url": _literal_tex_url(arg), "url_source":arg, "s": arg,
                                   "o_start": base + i, "o_end": base + k2})
                    i = k2
                    continue
                if name in {"textsuperscript", "textsubscript", "footnote"}:
                    kind = {"textsuperscript": "sup", "textsubscript": "sub",
                            "footnote": "footnote"}[name]
                    nested = tex_pieces(arg, known_macros, base=base + k + 1)
                    flush(i)
                    pieces.append({"t": kind, "s": _flatten_pieces(nested), "pieces": nested,
                                   "o_start": base + i, "o_end": base + k2})
                    i = k2
                    continue
                if name in _REF_CMDS:
                    flush(i)
                    pieces.append({"t": "ref", "label": arg.strip(), "cmd": name,
                                   "o_start": base + i, "o_end": base + k2})
                    i = k2
                    continue
                if name in _EMPH_CMDS or name in _BOLD_CMDS or name in _CODE_CMDS \
                        or name in _PLAIN_CMDS:
                    kind = ("emph" if name in _EMPH_CMDS else
                            "bold" if name in _BOLD_CMDS else
                            "code" if name in _CODE_CMDS else "text")
                    inner = _flatten_pieces(tex_pieces(arg, known_macros))
                    flush(i)
                    if inner:
                        pieces.append({"t": kind, "s": inner,
                                       "pieces": tex_pieces(arg, known_macros, base=base + k + 1),
                                       "o_start": base + i, "o_end": base + k2})
                    i = k2
                    continue
            args: list[str] = []
            k3 = k
            while k3 < n and tex[k3] == "{":
                a, k3 = _brace_arg(tex, k3)
                args.append(a)
            flush(i)
            pieces.append({"t": "macro", "name": name, "s": tex[i:k3],
                           "args": args, "known": ("\\" + name) in known_macros,
                           "o_start": base + i, "o_end": base + k3})
            i = k3
            continue
        push(c, i)
        i += 1
    flush(n)
    return pieces


def _flatten_pieces(pieces: list[dict]) -> str:
    """The plain string a nested group reads as (``\\emph{…}``'s ``s``). Math keeps its
    dollars so the surface can still render it; a macro keeps its verbatim source."""
    out: list[str] = []
    for p in pieces:
        t = p.get("t")
        if t in ("text", "emph", "bold", "code", "symbol", "placeholder",
                 "sup", "sub", "provenance-label"):
            out.append(p.get("s") or "")
        elif t in {"semantic-label", "algorithm", "footnote", "parbox", "group", "href"}:
            out.append(_flatten_pieces(p.get("pieces") or []))
        elif t == "algorithm-keyword":
            out.append((p.get("s") or "") + _flatten_pieces(p.get("pieces") or []))
        elif t == "break":
            out.append(" ")
        elif t == "math":
            out.append("$" + (p.get("s") or "") + "$")
        elif t in {"macro", "raw", "unknown"}:
            out.append(p.get("s") or "")
        elif t == "url":
            out.append(p.get("s") or "")
        elif t == "cite":
            out.append("[" + ", ".join(p.get("keys") or []) + "]")
        elif t == "ref":
            out.append(p.get("label") or "")
    return "".join(out)


def _presentation_only(pieces: list[dict]) -> bool:
    seen = False
    def has_content(rows):
        nonlocal seen
        for row in rows:
            if row.get('t') == 'presentation': seen = True
            elif row.get('t') == 'group':
                if has_content(row.get('pieces') or []): return True
            elif row.get('t') == 'break': continue
            elif row.get('t') == 'text' and not (row.get('s') or '').strip(): continue
            else: return True
        return False
    content = has_content(pieces)
    return seen and not content


# ---------------------------------------------------------------------------
# the block model — one fragment file's source as addressable blocks
# ---------------------------------------------------------------------------

_HEAD_RE = re.compile(r"^\s*\\(part|chapter|section|subsection|subsubsection|paragraph|subparagraph)(\*?)\s*(?:\[[^]]*\]\s*)?\{")
_BEGIN_RE = re.compile(r"^\s*\\begin\s*\{([A-Za-z@][A-Za-z0-9@:_*\-]*)\}")
_LABEL_ONLY_RE = re.compile(r"^\s*\\label\s*\{([^}]*)\}\s*$")
_LABEL_ANY_RE = re.compile(r"\\label\s*\{([^}]*)\}")


def _equation_math(inner: str) -> tuple[str, list[dict]]:
    """Keep label positions in rendered math, separately from exact source spans."""
    parts, labels, end, offset = [], [], 0, 0
    for match in _LABEL_ANY_RE.finditer(inner):
        before = inner[end:match.start()]
        parts.append(before)
        # The browser slices UTF-16 strings; source-piece offsets remain unchanged.
        offset += len(before.encode('utf-16-le')) // 2
        labels.append({'label': match.group(1), 'offset': offset})
        end = match.end()
    parts.append(inner[end:])
    return ''.join(parts), labels
_INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{")

_MATH_ENVS = frozenset({
    "equation", "equation*", "align", "align*", "gather", "gather*",
    "multline", "multline*", "eqnarray", "eqnarray*", "displaymath",
    "flalign", "flalign*", "alignat", "alignat*",
})
_FIGURE_ENVS = frozenset({"figure", "figure*", "wrapfigure"})
_THEOREM_ENVS = frozenset({"theorem", "lemma", "proposition", "corollary", "definition", "remark", "proof", "example", "assumption"})
_TABLE_ENVS = frozenset({"table", "table*", "tabular", "tabular*", "ruledtabular", "longtable"})
_READABLE_WRAPPERS = frozenset({"explained", "explanation", "algorithm", "center", "thebibliography"})

#: THE LIST GRAMMAR (GAP-20260810-raw-block-fidelity). ``itemize`` / ``enumerate`` /
#: ``description`` are prose the author redlines — they were shown as marked raw source,
#: honest but unreadable, and a rewrite inside one had no rendered face to type over. They
#: are now typed: each item tokenized through the SAME piece pipeline the prose uses (so
#: math, citations and cross-refs inside an item render and carry their source offsets),
#: nested ONE level. ``table``/``tabular`` deliberately stay ``kind:"raw"``: a table's
#: grammar is column-and-rule geometry, and a half-rendered table would be a lie about
#: fidelity where the raw badge is the truth.
_LIST_ENVS = frozenset({"itemize", "enumerate", "description"})
#: one scanner for the list grammar: a nested list opens/closes, an ``\item`` at depth 0
#: starts an item. Written once so the split and the nesting can never disagree.
_LIST_TOKEN_RE = re.compile(
    r"\\(begin|end)\s*\{(itemize|enumerate|description)\}|\\item\b")
_LIST_BEGIN_ONE_RE = re.compile(r"\\begin\s*\{(itemize|enumerate|description)\}")


def _list_env_end(s: str, at: int, env: str) -> int:
    """The index just past the ``\\end{env}`` closing the ``\\begin{env}`` that starts at
    ``at``, nesting counted. Unclosed -> ``len(s)`` (a partial result, never a raise)."""
    depth = 0
    for m in _LIST_TOKEN_RE.finditer(s, at):
        g = m.group(1)
        if g == "begin":
            depth += 1
        elif g == "end":
            depth -= 1
            if depth <= 0:
                return m.end()
    return len(s)


def list_items(inner: str, known_macros: frozenset[str] = frozenset(),
               base: int = 0, depth: int = 0) -> list[dict]:
    """One list body's ``\\item``s, in order.

    ``[{tex, pieces, term, term_pieces?, sub?, tail_pieces?}]`` — ``pieces`` is the item's
    prose through :func:`tex_pieces` (offsets shifted by ``base``, so they still address
    the BLOCK's tex), ``term`` is a ``description`` list's optional ``\\item[…]`` label,
    ``sub`` is one nested list (``{env, ordered, items}``) and ``tail_pieces`` is whatever
    prose follows it. Nesting stops at ONE level: a list inside a nested list stays inside
    its item's pieces as macro pieces, marked, never dropped."""
    marks: list[tuple[int, int]] = []
    lvl = 0
    for m in _LIST_TOKEN_RE.finditer(inner):
        g = m.group(1)
        if g == "begin":
            lvl += 1
        elif g == "end":
            lvl = max(0, lvl - 1)
        elif lvl == 0:
            marks.append((m.start(), m.end()))
    out: list[dict] = []
    for idx, (_istart, cstart) in enumerate(marks):
        cend = marks[idx + 1][0] if idx + 1 < len(marks) else len(inner)
        body = inner[cstart:cend]
        off = cstart
        lead = len(body) - len(body.lstrip(" \t\n"))
        term = ""
        if lead < len(body) and body[lead] == "[":
            term, past = _opt_arg(body, lead)
            body, off = body[past:], off + past
        item: dict[str, Any] = {"tex": inner[cstart:cend], "term": term,
                                "o_start": base + cstart, "o_end": base + cend}
        if term:
            item["term_pieces"] = tex_pieces(term, known_macros,
                                             base=base + cstart + lead + 1)
        sub_env, sub_lo, sub_hi, past_end = "", 0, 0, len(body)
        head_hi = len(body)
        if depth < 16:
            mb = _LIST_BEGIN_ONE_RE.search(body)
            if mb is not None:
                sub_env = mb.group(1)
                past_end = _list_env_end(body, mb.start(), sub_env)
                head_hi = mb.start()
                sub_lo = mb.end()
                lead = sub_lo
                while lead < len(body) and body[lead].isspace():
                    lead += 1
                _options, past_options = _opt_arg(body, lead)
                if past_options != lead:
                    sub_lo = past_options
                close = body.rfind("\\end", mb.start(), past_end)
                sub_hi = close if close > sub_lo else past_end
        item["pieces"] = tex_pieces(body[:head_hi], known_macros, base=base + off)
        if sub_env:
            item["sub"] = {"env": sub_env, "ordered": sub_env == "enumerate",
                           "items": list_items(body[sub_lo:sub_hi], known_macros,
                                               base=base + off + sub_lo, depth=depth + 1)}
            if body[past_end:].strip():
                item["tail_pieces"] = tex_pieces(body[past_end:], known_macros,
                                                 base=base + off + past_end)
        out.append(item)
    return out

#: the image extensions TeX will have tried, in the order graphicx prefers them. A figure
#: argument written without a suffix is resolved by probing these.
_IMAGE_EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg", ".gif")

_ASSET_TYPES = {".pdf": "application/pdf", ".png": "image/png",
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".svg": "image/svg+xml", ".gif": "image/gif",
                ".eps": "application/postscript"}


def _masked_tex_comments(tex: str, known_macros=frozenset(), *, literal_spans=None,
                         opaque_spans=None) -> str:
    """Inert comments/literal paths, retaining every character and line position."""
    masked, cursor = [], 0
    for match in re.finditer(r"%|\\path(?![A-Za-z@])", tex):
        start = match.start()
        if start < cursor:
            continue
        if match.group().startswith("\\"):
            literal = _path_literal(tex, start, known_macros)
            if literal is None:
                command = _CTRL_WORD_RE.match(tex, start)
                prior = start - 1
                while prior >= 0 and tex[prior] == "\\":
                    prior -= 1
                active = (start - prior - 1) % 2 == 0
                if opaque_spans is not None and active and command and command.group(1) == 'path':
                    opaque_spans.append((start, _path_source_end(tex, start)))
                continue
            _content, end = literal
            if literal_spans is not None:
                literal_spans.append((start, end))
        else:
            prior = start - 1
            while prior >= 0 and tex[prior] == "\\":
                prior -= 1
            if (start - prior - 1) % 2:
                continue
            end = tex.find("\n", start)
            end = len(tex) if end < 0 else end
        masked.append(tex[cursor:start])
        masked.append(re.sub(r"[^\r\n]", " ", tex[start:end]))
        cursor = end
    masked.append(tex[cursor:])
    return "".join(masked)


class _StructuralLines(list):
    """Ephemeral masked source and line addresses shared by one parse pass."""
    def __init__(self, text: str):
        super().__init__(text.split("\n"))
        self.text = text
        self.offsets = [0, *(match.end() for match in re.finditer("\n", text))]


def _structural_pass(tex: str, lines: list[str], known_macros=frozenset()) -> tuple[list[str], list[bool]]:
    """One ephemeral mask and prefix-location projection per source pass."""
    literal, opaque = [], []
    masked = _masked_tex_comments(tex, known_macros, literal_spans=literal, opaque_spans=opaque)
    spans = sorted(literal + opaque)
    prefixes, offset, cursor, past = [], 0, 0, -1
    for line in lines:
        prefix = offset + len(line) - len(line.lstrip())
        while cursor < len(spans) and spans[cursor][0] <= prefix:
            past = max(past, spans[cursor][1])
            cursor += 1
        prefixes.append(prefix < past)
        offset += len(line) + 1
    return _StructuralLines(masked), prefixes


def _env_end_line(lines: list[str], i: int, env: str, known_macros=frozenset(),
                  *, masked_lines: list[str] | None = None) -> int:
    """The 0-based index of the line closing ``\\begin{env}`` opened on line ``i``, counting
    nested opens of the same environment. Unclosed -> the last line (a partial result)."""
    if masked_lines is None:
        masked_lines = _StructuralLines(_masked_tex_comments("\n".join(lines), known_macros))
    elif not isinstance(masked_lines, _StructuralLines):
        masked_lines = _StructuralLines("\n".join(masked_lines))
    token = re.compile(r"\\(begin|end)\s*\{" + re.escape(env) + r"\}")
    depth = 0
    # Use the already-masked source so whitespace inside a delimiter can cross
    # lines. Scan only this balanced environment, without remasking/copying the
    # document suffix or repeatedly counting its preceding lines.
    for match in token.finditer(masked_lines.text, masked_lines.offsets[i]):
        if match.group(1) == "begin":
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0:
                return bisect_right(masked_lines.offsets, match.end() - 1) - 1
    return len(lines) - 1


def _environment_body(tex: str, env: str, start: int = 0, *, known_macros=frozenset()) -> tuple[str, int, int] | None:
    """Return the exact body and half-open offsets of one balanced environment.

    Unlike line slicing, this retains prose that shares either delimiter's line.
    ``None`` is the honest unbalanced result; callers render the whole block as source.
    """
    token = re.compile(r"\\(begin|end)\s*\{" + re.escape(env) + r"\}")
    depth = 0
    body_start = None
    for match in token.finditer(_masked_tex_comments(tex, known_macros), start):
        if match.group(1) == "begin":
            if depth == 0:
                body_start = match.end()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0 and body_start is not None:
                return tex[body_start:match.start()], body_start, match.start()
    return None


def _environment_number_labels(inner: str, known_macros=frozenset()) -> list[str]:
    """Labels on this environment, excluding nested equation/list counters."""
    token = re.compile(r"\\(?:(begin|end)\s*\{[^}]+\}|label\s*\{([^}]+)\})")
    labels, depth = [], 0
    for match in token.finditer(_masked_tex_comments(inner, known_macros)):
        if match.group(1) == "begin":
            depth += 1
        elif match.group(1) == "end":
            depth = max(0, depth - 1)
        elif depth == 0:
            labels.append(match.group(2))
    return labels


def _title_chrome(template: str, known_macros) -> tuple[str, str]:
    """Literal declaration chrome around one source-mapped environment title.

    ``#1`` is the environment's authored argument.  It is intentionally not
    folded into ``title_pieces``: those offsets must keep pointing only at the
    argument in the manuscript source.
    """
    if not isinstance(template, str) or template.count("#1") != 1:
        return "", ""
    prefix, suffix = template.split("#1", 1)
    return (_flatten_pieces(tex_pieces(prefix, known_macros)),
            _flatten_pieces(tex_pieces(suffix, known_macros)))


def _algorithm_commands(tex: str, labels: dict[str, str]) -> list[tuple[int, int, str]]:
    """Declared algorithmic commands at lexical top level.

    Commands in comments, math, nested environments, escaped source, or another
    macro's argument are content of that construct rather than algorithm grammar.
    """
    pattern = re.compile(r"\\(" + "|".join(sorted(labels, key=len, reverse=True)) + r")\b")
    found: list[tuple[int, int, str]] = []
    i = braces = 0
    math = ""
    environments: list[str] = []
    while i < len(tex):
        if tex[i] == "%" and (i == 0 or tex[i - 1] != "\\"):
            newline = tex.find("\n", i)
            i = len(tex) if newline < 0 else newline + 1
            continue
        if tex.startswith("\\begin", i) or tex.startswith("\\end", i):
            environment = re.match(r"\\(begin|end)\s*\{([^}]+)\}", tex[i:])
            if environment:
                if environment.group(1) == "begin":
                    environments.append(environment.group(2))
                elif environments and environments[-1] == environment.group(2):
                    environments.pop()
                i += environment.end()
                continue
        if tex[i] == "\\":
            pair = tex[i:i + 2]
            if pair in {"\\(", "\\["}:
                math = "\\)" if pair == "\\(" else "\\]"
                i += 2
                continue
            if math and pair == math:
                math = ""
                i += 2
                continue
            if not math and not environments and braces == 0:
                match = pattern.match(tex, i)
                if match:
                    found.append((match.start(), match.end(), match.group(1)))
                    i = match.end()
                    continue
            i += min(2, len(tex) - i)
            continue
        if tex[i] == "$":
            token = "$$" if tex.startswith("$$", i) else "$"
            math = "" if math == token else token
            i += len(token)
            continue
        if not math and not environments:
            if tex[i] == "{":
                braces += 1
            elif tex[i] == "}":
                braces = max(0, braces - 1)
        i += 1
    return found


def bibliography_items(inner: str, known_macros, base: int = 0) -> list[dict]:
    """Authored bibitems as readable entries with offsets into their enclosing block."""
    marks = _algorithm_commands(inner, {"bibitem":""})
    items = []
    for index, (start, command_end, _name) in enumerate(marks):
        cursor = command_end
        while cursor < len(inner) and inner[cursor].isspace(): cursor += 1
        label_start = cursor
        label, after_label = _opt_arg(inner, cursor)
        if after_label != cursor:
            cursor = after_label
            while cursor < len(inner) and inner[cursor].isspace(): cursor += 1
        key, after_key = _brace_arg(inner, cursor)
        if after_key == cursor or not key.strip():
            # Invalid bibitem syntax remains inspectable source rather than losing text.
            return []
        end = marks[index + 1][0] if index + 1 < len(marks) else len(inner)
        items.append({"bibliography":True, "key":key.strip(),
            "term":label if after_label != label_start else str(index+1),
            "term_pieces":tex_pieces(label, known_macros, base + label_start + 1)
                if after_label != label_start else [],
            "tex":inner[after_key:end], "o_start":base+after_key, "o_end":base+end,
            "pieces":tex_pieces(inner[after_key:end], known_macros, base+after_key)})
    return items


def algorithm_pieces(tex: str, known_macros, base: int = 0) -> list[dict]:
    """Algorithmicx control words, with conditions/comments kept as typed content.

    Only the declared grammar is transformed. Unknown commands remain source
    through tex_pieces; all outer offsets address the original algorithm body.
    """
    labels = {"State": "", "Require": "Require: ", "Ensure": "Ensure: ",
              "If": "if ", "ElsIf": "else if ", "Else": "else",
              "EndIf": "end if", "For": "for ", "ForAll": "for each ",
              "EndFor": "end for", "While": "while ", "EndWhile": "end while",
              "Repeat": "repeat", "Until": "until ", "Return": "return ",
              "Comment": " ▷ ", "Function": "function ", "EndFunction": "end function",
              "Procedure": "procedure ", "EndProcedure": "end procedure"}
    pieces, cursor = [], 0
    for start, match_end, name in _algorithm_commands(tex, labels):
        if start < cursor:
            continue
        pieces.extend(tex_pieces(tex[cursor:start], known_macros, base + cursor))
        end = match_end
        while end < len(tex) and tex[end] in " \t":
            end += 1
        part = {"t": "algorithm-keyword", "s": labels[name],
                "new_line": name not in {"Return", "Comment"},
                "o_start": base + start}
        if end < len(tex) and tex[end] == "{":
            arg, past = _brace_arg(tex, end)
            part["pieces"] = tex_pieces(arg, known_macros, base + end + 1)
            end = past
        part["o_end"] = base + end
        pieces.append(part)
        cursor = end
    pieces.extend(tex_pieces(tex[cursor:], known_macros, base + cursor))
    return pieces


def _split_tex_top(tex: str, separator: str, known_macros=frozenset()) -> tuple[list[tuple[str, int, int]], bool]:
    """Split top-level table rows/cells, respecting braces, math, escapes and nested envs."""
    original, tex = tex, _masked_tex_comments(tex, known_macros)
    parts: list[tuple[str, int, int]] = []
    start, i, braces = 0, 0, 0
    math = ""
    environments: list[str] = []
    while i < len(tex):
        if tex[i] == "%" and (i == 0 or tex[i - 1] != "\\"):
            newline = tex.find("\n", i)
            i = len(tex) if newline < 0 else newline + 1
            continue
        if tex.startswith("\\begin", i) or tex.startswith("\\end", i):
            match = re.match(r"\\(begin|end)\s*\{([^}]+)\}", tex[i:])
            if match:
                if match.group(1) == "begin":
                    environments.append(match.group(2))
                elif environments and environments[-1] == match.group(2):
                    environments.pop()
                i += match.end()
                continue
        if tex[i] == "\\":
            pair = tex[i:i + 2]
            if pair in {"\\(", "\\["}:
                math = "\\)" if pair == "\\(" else "\\]"
                i += 2
                continue
            if math and pair == math:
                math = ""
                i += 2
                continue
            if separator == "row" and pair == "\\\\" and braces == 0 and not math and not environments:
                parts.append((original[start:i], start, i))
                i += 2
                if i < len(tex) and tex[i] == "[":
                    _ignored, i = _opt_arg(tex, i)
                start = i
                continue
            i += min(2, len(tex) - i)
            continue
        if tex[i] == "$":
            marker = "$$" if tex.startswith("$$", i) else "$"
            math = "" if math == marker else marker
            i += len(marker)
            continue
        if not math and not environments:
            if tex[i] == "{":
                braces += 1
            elif tex[i] == "}":
                braces -= 1
                if braces < 0:
                    return [], False
            elif separator == "cell" and tex[i] == "&" and braces == 0:
                parts.append((original[start:i], start, i))
                start = i + 1
        i += 1
    parts.append((original[start:], start, len(tex)))
    return parts, braces == 0 and not math and not environments


_TABLE_EDGE_CONTROL = re.compile(
    r"^\s*(?:\\(?:hline|toprule|midrule|bottomrule)\b\s*|\\addlinespace(?:\[[^]]*\])?\s*|"
    r"\\(?:cline|cmidrule)(?:\([^)]*\))?\s*\{[^}]*\}\s*)")


def _trim_table_controls(tex: str, offset: int) -> tuple[str, int]:
    while True:
        match = _TABLE_EDGE_CONTROL.match(tex)
        if match is None:
            break
        offset += match.end()
        tex = tex[match.end():]
    lead = len(tex) - len(tex.lstrip())
    tex, offset = tex.strip(), offset + lead
    while True:
        match = re.search(
            r"(?:\\(?:hline|toprule|midrule|bottomrule)\b\s*|\\addlinespace(?:\[[^]]*\])?\s*|"
            r"\\(?:cline|cmidrule)(?:\([^)]*\))?\s*\{[^}]*\}\s*)$", tex)
        if match is None:
            break
        tex = tex[:match.start()].rstrip()
    return tex, offset


def _table_cell(tex: str, offset: int, known_macros: frozenset[str]) -> dict | None:
    tex, offset = _trim_table_controls(tex, offset)
    if not tex:
        return {"tex": "", "pieces": [], "colspan": 1, "align": "",
                "o_start": offset, "o_end": offset}
    colspan, align, content, content_offset = 1, "", tex, offset
    match = re.match(r"\\multicolumn\s*", tex)
    if match:
        cursor = match.end()
        try:
            count, cursor = _brace_arg(tex, cursor)
            align, cursor = _brace_arg(tex, cursor)
            content, cursor = _brace_arg(tex, cursor, require_closed=True, known_macros=known_macros)
        except (ValueError, IndexError):
            return None
        if tex[cursor:].strip() or not count.strip().isdigit() or int(count) < 1:
            return None
        colspan = int(count)
        content_start = tex.find("{", tex.find("{", tex.find("{", match.end()) + 1) + 1) + 1
        content_offset = offset + content_start
    pieces = tex_pieces(content, known_macros, base=content_offset)
    pending = list(pieces)
    while pending:
        piece = pending.pop()
        if piece.get('t') == 'raw' and piece.get('command') == 'path':
            return None  # unknown literal boundaries must not guess row/cell separators
        pending.extend(piece.get('pieces') or [])
    return {"tex": content, "pieces": pieces,
            "colspan": colspan, "align": align, "o_start": content_offset,
            "o_end": content_offset + len(content)}


def _longtable_markers(tex: str, known_macros=frozenset()) -> list[tuple[int, int, str]]:
    """Top-level longtable section terminators, never commands inside a cell group."""
    tex = _masked_tex_comments(tex, known_macros)
    names = re.compile(r"\\end(firsthead|head|foot|lastfoot)\b")
    markers: list[tuple[int, int, str]] = []
    i = braces = 0
    math = ""
    environments: list[str] = []
    while i < len(tex):
        if tex[i] == "%" and (i == 0 or tex[i - 1] != "\\"):
            newline = tex.find("\n", i)
            i = len(tex) if newline < 0 else newline + 1
            continue
        if tex.startswith("\\begin", i) or tex.startswith("\\end", i):
            environment = re.match(r"\\(begin|end)\s*\{([^}]+)\}", tex[i:])
            if environment:
                if environment.group(1) == "begin":
                    environments.append(environment.group(2))
                elif environments and environments[-1] == environment.group(2):
                    environments.pop()
                i += environment.end()
                continue
        if tex[i] == "\\":
            pair = tex[i:i + 2]
            if pair in {"\\(", "\\["}:
                math = "\\)" if pair == "\\(" else "\\]"
                i += 2
                continue
            if math and pair == math:
                math = ""
                i += 2
                continue
            if not math and not environments and braces == 0:
                marker = names.match(tex, i)
                if marker:
                    markers.append((marker.start(), marker.end(), marker.group(1)))
                    i = marker.end()
                    continue
            i += min(2, len(tex) - i)
            continue
        if tex[i] == "$":
            token = "$$" if tex.startswith("$$", i) else "$"
            math = "" if math == token else token
            i += len(token)
            continue
        if not math and not environments:
            if tex[i] == "{":
                braces += 1
            elif tex[i] == "}":
                braces = max(0, braces - 1)
        i += 1
    return markers


def _strip_longtable_caption(inner: str, base: int) -> tuple[str, int]:
    """Remove a leading caption/label row already represented by caption_pieces."""
    lead = len(inner) - len(inner.lstrip())
    match = _CAPTION_RE.match(inner, lead)
    if match is None:
        return inner, base
    try:
        _caption, cursor = _brace_arg(inner, match.end() - 1)
    except (ValueError, IndexError):
        return inner, base
    while True:
        whitespace = re.match(r"\s*", inner[cursor:])
        cursor += whitespace.end() if whitespace else 0
        label = re.match(r"\\label\s*\{[^}]*\}", inner[cursor:])
        if label is None:
            break
        cursor += label.end()
    whitespace = re.match(r"\s*", inner[cursor:])
    cursor += whitespace.end() if whitespace else 0
    if inner.startswith("\\\\", cursor):
        cursor += 2
        if cursor < len(inner) and inner[cursor] == "[":
            _ignored, cursor = _opt_arg(inner, cursor)
    return inner[cursor:], base + cursor


def _longtable_segments(inner: str, base: int, known_macros=frozenset()) -> list[tuple[str, str, int]]:
    markers = _longtable_markers(inner, known_macros)
    if not markers:
        return [("body", inner, base)]
    role_for_end = {"firsthead": "first-header", "head": "continuation-header",
                    "foot": "continuation-footer", "lastfoot": "final-footer"}
    segments: list[tuple[str, str, int]] = []
    cursor = 0
    for start, end, name in markers:
        if start < cursor:
            continue
        segments.append((role_for_end[name], inner[cursor:start], base + cursor))
        cursor = end
    segments.append(("body", inner[cursor:], base + cursor))
    return segments


def _table_rows(inner: str, base: int, role: str,
                known_macros: frozenset[str]) -> list[dict] | None:
    row_parts, valid = _split_tex_top(inner, "row", known_macros)
    if not valid:
        return None
    midrule = re.search(r"\\midrule\b", _masked_tex_comments(inner, known_macros))
    rows: list[dict] = []
    for row_tex, row_start, row_end in row_parts:
        row_tex, adjusted = _trim_table_controls(row_tex, base + row_start)
        if not row_tex:
            continue
        cells_raw, valid = _split_tex_top(row_tex, "cell", known_macros)
        if not valid:
            return None
        cells = []
        for cell_tex, cell_start, _cell_end in cells_raw:
            cell = _table_cell(cell_tex, adjusted + cell_start, known_macros)
            if cell is None:
                return None
            cells.append(cell)
        header = role in {"first-header", "continuation-header"} or bool(
            midrule and row_end <= midrule.start()) or all(
            cell.get("tex", "").lstrip().startswith("\\textbf") for cell in cells)
        rows.append({"cells": cells, "header": header, "role": role,
                     "o_start": adjusted, "o_end": adjusted + len(row_tex)})
    return rows


_TABLE_CONTAINERS = frozenset({"table", "table*", "ruledtabular", "center"})
_TABLE_LAYOUT_CONTROL = re.compile(
    r"\\(?:centering|tiny|scriptsize|footnotesize|small|normalsize|large|Large|LARGE|huge|Huge)\b")


def _table_padding_end(tex: str, cursor: int = 0, known_macros=frozenset()) -> int:
    """Skip only known inert layout/metadata; never hide surrounding prose."""
    while cursor < len(tex):
        padding = re.match(r"(?:\s+|%[^\n]*(?:\n|$))", tex[cursor:])
        if padding:
            cursor += padding.end()
            continue
        control = _TABLE_LAYOUT_CONTROL.match(tex, cursor)
        if control:
            cursor = control.end()
            continue
        caption = _CAPTION_RE.match(tex, cursor)
        label = re.match(r"\\label\s*\{", tex[cursor:])
        if caption or label:
            opening = caption.end() - 1 if caption else cursor + label.end() - 1
            content, past = _brace_arg(tex, opening, known_macros=known_macros)
            if past <= opening or tex[past - 1:past] != "}" or not _split_tex_top(content, "cell", known_macros)[1]:
                break
            cursor = past
            continue
        break
    return cursor


def _single_table_body(tex: str, base: int, depth: int = 0, known_macros=frozenset()) -> tuple[str, str, int] | None:
    """One table inside layout containers/groups, retaining original offsets."""
    if depth >= 16:
        return None
    cursor = _table_padding_end(tex, known_macros=known_macros)
    if cursor < len(tex) and tex[cursor] == "{":
        group, past = _brace_arg(tex, cursor, known_macros=known_macros)
        if (tex[past - 1:past] != "}" or _table_padding_end(tex, past, known_macros) != len(tex)
                or not _split_tex_top(group, "cell", known_macros)[1]):
            return None
        return _single_table_body(group, base + cursor + 1, depth + 1, known_macros)
    opening = re.match(r"\\begin\s*\{([^}]+)\}", tex[cursor:])
    if not opening or opening.group(1) not in _TABLE_ENVS | _TABLE_CONTAINERS:
        return None
    env = opening.group(1)
    info = _environment_body(tex, env, cursor, known_macros=known_macros)
    if info is None:
        return None
    inner, inner_base, close = info
    # Match the same inert-comment spelling used to locate this delimiter;
    # offsets still address the original bytes, including split closing lines.
    ending = re.match(r"\\end\s*\{" + re.escape(env) + r"\}",
                      _masked_tex_comments(tex, known_macros)[close:])
    if not ending or _table_padding_end(tex, close + ending.end(), known_macros) != len(tex):
        return None
    if env in _TABLE_CONTAINERS:
        if env in {"table", "table*"}:
            lead = len(inner) - len(inner.lstrip())
            _placement, past = _opt_arg(inner, lead)
            if past != lead:
                inner, inner_base = inner[past:], inner_base + past
        return _single_table_body(inner, base + inner_base, depth + 1, known_macros)
    return env, inner, base + inner_base


def _table_payload(block: str, env: str, known_macros: frozenset[str]) -> list[dict] | None:
    # The existing client has one caption face. Multiple authored captions must
    # remain inspectable source rather than losing a second visible meaning.
    if len(list(_CAPTION_RE.finditer(_masked_tex_comments(block, known_macros)))) > 1:
        return None
    nested = _single_table_body(block, 0, known_macros=known_macros)
    if nested is None:
        return None
    table_env, inner, base = nested
    if table_env in {"tabular", "tabular*", "longtable"}:
        lead = len(inner) - len(inner.lstrip())
        cursor = lead
        # tabular* may carry a width before the column declaration.
        args = 2 if table_env == "tabular*" else 1
        try:
            for _ in range(args):
                if cursor >= len(inner) or inner[cursor] != "{":
                    return None
                _argument, cursor = _brace_arg(inner, cursor)
                while cursor < len(inner) and inner[cursor].isspace():
                    cursor += 1
        except (ValueError, IndexError):
            return None
        inner, base = inner[cursor:], base + cursor
    rows: list[dict] = []
    segments = [("body", inner, base)]
    if table_env == "longtable":
        inner, base = _strip_longtable_caption(inner, base)
        segments = _longtable_segments(inner, base, known_macros)
    seen_headers: set[tuple] = set()
    seen_footers: set[tuple] = set()
    for role, segment, segment_base in segments:
        parsed = _table_rows(segment, segment_base, role, known_macros)
        if parsed is None:
            return None
        for row in parsed:
            signature = tuple((cell.get("tex"), cell.get("colspan"), cell.get("align"))
                              for cell in row["cells"])
            if role == "continuation-header" and signature in seen_headers:
                continue
            if role in {"first-header", "continuation-header"}:
                seen_headers.add(signature)
            if role == "final-footer" and signature in seen_footers:
                continue
            if role in {"continuation-footer", "final-footer"}:
                seen_footers.add(signature)
            rows.append(row)
    return rows or None


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "section"


def _para_index(spans: list[dict]) -> list[tuple[int, int, str, str]]:
    """``parse_paragraphs`` spans as ``(start_line, end_line, spec_id, section)`` tuples —
    the one producer of paragraph grain (``projection_viewer.parse_paragraphs``), read
    here rather than re-derived."""
    return [(int(s.get("start_line") or 0), int(s.get("end_line") or 0),
             str(s.get("spec_id") or ""), str(s.get("section") or ""))
            for s in spans]


def _para_at(index: list[tuple[int, int, str, str]], line: int) -> tuple[str, str]:
    for lo, hi, sid, sec in index:
        if lo <= line <= hi:
            return sid, sec
    return "", ""


def _trust_root(corpus: str, dir_param: str, md: Path) -> Path:
    """The one directory the walk will resolve and serve figure bytes from.

    The manuscript dir by default — and ALWAYS for a raw ``?dir=`` request, which names
    an arbitrary repo path and is never widened. A corpus-addressed request widens to the
    registry row's declared ``project_dir``, because TeX resolves
    ``\\includegraphics{../figures/x}`` against the project, not the manuscript. The
    widening is bounded three ways: the project_dir is fenced under the repo root, a
    ``project_dir`` of ``.`` (the repo itself) never widens, and a project_dir that does
    not actually contain the manuscript dir never widens. One root, used by BOTH
    :func:`_resolve_image` and :func:`asset`, so what the model routes is exactly what the
    door serves."""
    if dir_param or not corpus:
        return md
    try:
        from laplace.pipeline import registry
        proj = registry.resolve(corpus)
    except Exception:                                  # a registry hiccup never widens
        return md
    pd = (getattr(proj, "project_dir", "") or "").strip().strip("/") if proj else ""
    if not pd or pd == "." or Path(pd).is_absolute() or ".." in Path(pd).parts:
        return md
    try:
        root = (_repo_root().resolve() / pd).resolve()
        root.relative_to(_repo_root().resolve())       # never outside the repo
        md.resolve().relative_to(root)                 # must actually contain the md
    except (ValueError, OSError):
        return md
    return root if root.is_dir() else md


def _resolve_image(md: Path, arg: str, root: Path | None = None) -> tuple[Path | None, str]:
    """The on-disk asset a ``\\includegraphics`` argument names, resolved the way TeX does
    (relative to the manuscript dir, extension probed when the argument carries none) and
    then PINNED under the trust root (:func:`_trust_root`; the manuscript dir when none is
    given). A hit that lands outside the root — an absolute argument, or a ``..`` walk past
    it — is refused, not served. Returns ``(path|None, root-relative posix)``."""
    arg = (arg or "").strip()
    if not arg:
        return None, ""
    fence = (root or md).resolve()
    roots = [md]
    # graphicx resolves bare image names through the root document's declared
    # graphicspath entries.  Read only that declaration; every candidate still
    # has to remain under the established manuscript/project trust fence.
    main = md / "main.tex"
    try:
        match = re.search(r"\\graphicspath\s*\{\{([^{}]+)\}\}", main.read_text(encoding="utf-8", errors="replace"), re.S)
        if match:
            for entry in match.group(1).split('}{'):
                candidate = (md / entry.strip()).resolve()
                try:
                    candidate.relative_to((root or md).resolve())
                    if candidate.is_dir(): roots.append(candidate)
                except ValueError: pass
    except OSError: pass
    tries = []
    for image_root in roots:
        cand = image_root / arg
        tries += [cand] if cand.suffix else []
        tries += [cand.with_suffix(ext) if cand.suffix else Path(str(cand) + ext) for ext in _IMAGE_EXTS]
    for p in tries:
        try:
            if p.is_file():
                return p, p.resolve().relative_to(fence).as_posix()
        except (OSError, ValueError):
            continue
    return None, arg


def _asset_route(corpus: str, dir_param: str, rel: str) -> str:
    from urllib.parse import urlencode
    q = {"file": rel}
    if corpus:
        q["corpus"] = corpus
    if dir_param:
        q["dir"] = dir_param
    return "/walk/asset?" + urlencode(q)


def blocks_for(text: str, *, file_rel: str, repo_file: str, md: Path,
               corpus: str, dir_param: str, para_spans: list[dict],
               known_macros: frozenset[str], declared_envs: dict[str, str] | None = None,
               declared_presentation: dict[str, dict[str, str]] | None = None) -> list[dict]:
    """One fragment's source as blocks, in document order.

    Line numbers are 1-based inclusive over ``text.split("\\n")`` — the SAME split the
    rewrite door's byte guard uses, so ``block["tex"]`` is byte-for-byte what
    ``"\\n".join(lines[line_start-1:line_end])`` reads back from disk. That identity is
    what makes the splice deterministic (the contract's whole point), and it is asserted
    in the fences.

    ``kind`` is one of ``para`` / ``equation`` / ``head`` / ``figure`` / ``caption`` /
    ``raw``. ``raw`` is the plain fallback for a construct the parser cannot type: it is
    shown as source and stays fully addressable."""
    lines = text.split("\n")
    masked_lines, literal_prefixes = _structural_pass(text, lines, known_macros)
    declared_envs = declared_envs or {}
    declared_presentation = declared_presentation or {}
    index = _para_index(para_spans)
    troot = _trust_root(corpus, dir_param, md)
    out: list[dict] = []
    ordinal = 0
    pid_seen: dict[str, int] = {}

    def emit(kind: str, lo: int, hi: int, **extra: Any) -> dict:
        nonlocal ordinal
        ordinal += 1
        spec_id, section = _para_at(index, lo)
        spec_ids = list(dict.fromkeys(ident for span in para_spans
            if int(span.get("start_line") or 0) <= lo <= int(span.get("end_line") or 0)
            for ident in span.get("spec_ids", [span.get("spec_id")]) if isinstance(ident, str) and ident))
        if spec_id:
            pid_seen[spec_id] = pid_seen.get(spec_id, 0) + 1
            suffix = "" if pid_seen[spec_id] == 1 else f"-{pid_seen[spec_id]}"
            bid = f"{file_rel}#{spec_id}{suffix}"
        else:
            bid = f"{file_rel}#b{ordinal}"
        blk = {"id": bid, "kind": kind,
               "tex": "\n".join(lines[lo - 1:hi]),
               "src": {"file": file_rel, "repo_file": repo_file,
                       "line_start": lo, "line_end": hi},
               "spec_id": spec_id, "spec_ids": spec_ids, "section": section, "source_section": section}
        blk.update(extra)
        out.append(blk)
        return blk

    buf_start = 0                                  # 1-based line the prose run opened on
    i = 0
    n = len(lines)

    def flush(upto: int) -> None:
        nonlocal buf_start
        if buf_start and upto >= buf_start:
            chunk = "\n".join(lines[buf_start - 1:upto])
            if chunk.strip():
                pieces = tex_pieces(chunk, known_macros)
                emit("para", buf_start, upto,
                     pieces=pieces, presentation_only=_presentation_only(pieces),
                     labels=_LABEL_ANY_RE.findall(chunk))
        buf_start = 0

    while i < n:
        ln = lines[i]
        lineno = i + 1
        if (not ln.strip() or ln.lstrip().startswith("%")) and not literal_prefixes[i]:
            flush(lineno - 1)                      # blank line / structural comment
            i += 1
            continue
        if ln.strip() == r"\par" and not literal_prefixes[i]:
            # An authored `\par` on its own line is an intentional blank paragraph.
            # It stays addressable as this one exact source line so Enter at a paragraph
            # edge can create a normal editable destination without hidden markers.
            flush(lineno - 1)
            emit("para", lineno, lineno, pieces=tex_pieces(ln, known_macros), labels=[])
            i += 1
            continue
        opening = r"\[" if ln.lstrip().startswith(r"\[") else "$$" if ln.lstrip().startswith("$$") else None
        if opening and not literal_prefixes[i]:
            # A display owns its nested array/matrix environments. Splitting at
            # their \begin lines otherwise leaves visible literal \[ / \] blocks.
            remaining = "\n".join(lines[i:])
            begin = remaining.index(opening)
            closing = r"\]" if opening == r"\[" else "$$"
            stop = _find_math_close(remaining, begin + len(opening), closing)
            if stop < len(remaining):
                flush(lineno - 1)
                past = stop + len(closing)
                end = i + remaining[:past].count("\n")
                chunk = "\n".join(lines[i:end + 1])
                if chunk[past:].strip():
                    emit("para", lineno, end + 1, pieces=tex_pieces(chunk, known_macros),
                         labels=_LABEL_ANY_RE.findall(chunk))
                else:
                    math, equation_labels = _equation_math(remaining[begin + len(opening):stop])
                    emit("equation", lineno, end + 1, env="displaymath", math=math,
                         labels=[row['label'] for row in equation_labels],
                         equation_labels=equation_labels, number=None)
                i = end + 1
                continue
        mh = _HEAD_RE.match(ln)
        if mh and not literal_prefixes[i]:
            flush(lineno - 1)
            level = mh.group(1)
            brace = ln.index("{", mh.start(1))
            # Headings may span lines and may be followed by prose on the line
            # carrying the closing brace. Parse the balanced command over the
            # remaining source, then keep that tail in the SAME exact block span.
            remaining = "\n".join(lines[i:])
            title_tex, past = _brace_arg(remaining, brace)
            balanced = past > brace and past <= len(remaining) and remaining[past - 1:past] == "}"
            if not balanced:
                emit("raw", lineno, lineno, env=level,
                     reason="the unbalanced heading is shown as source")
                i += 1
                continue
            consumed_lines = remaining[:past].count("\n")
            end = i + consumed_lines
            relative_past = past
            label = ""
            adjacent_labels = []
            # A same-line label belongs to the heading. Preserve any following
            # prose as an addressed tail rather than dropping it behind the title.
            while True:
                whitespace = re.match(r"\s*", remaining[relative_past:])
                candidate = relative_past + (whitespace.end() if whitespace else 0)
                ml_inline = re.match(r"\\label\s*\{([^}]*)\}", remaining[candidate:])
                if ml_inline is None or "\n" in remaining[relative_past:candidate + ml_inline.end()]:
                    break
                label = ml_inline.group(1).strip()
                adjacent_labels.append(label)
                relative_past = candidate + ml_inline.end()
            tail_on_line = remaining[relative_past:remaining.find("\n", relative_past)
                                     if "\n" in remaining[relative_past:] else len(remaining)]
            while not tail_on_line.strip() and end + 1 < n:
                ml = _LABEL_ONLY_RE.match(lines[end + 1])
                if ml is None:
                    break
                label = ml.group(1).strip()
                adjacent_labels.append(label)
                end += 1
            tail_start = relative_past
            tail = tail_on_line
            # labels written inside the title braces belong to this heading too (its navigation identity)
            inline_labels = [value.strip() for value in _LABEL_ANY_RE.findall(title_tex)]
            emit("head", lineno, end + 1, level=level,
                 label=adjacent_labels[0] if adjacent_labels else (inline_labels[0] if inline_labels else ""),
                 labels=list(dict.fromkeys(inline_labels + adjacent_labels)),
                 title=_flatten_pieces(tex_pieces(title_tex, known_macros)),
                 title_tex=title_tex,
                 # the head's own tex opens on this line, so the title's content starts at
                 # `brace + 1` inside the block's tex: the pieces address it, not the title
                 # string in isolation.
                 pieces=tex_pieces(title_tex, known_macros, base=brace + 1),
                 title_pieces=tex_pieces(title_tex, known_macros, base=brace + 1),
                 tail=tail,
                 tail_pieces=tex_pieces(tail, known_macros, base=tail_start)
                 if tail.strip() else [])
            i = end + 1
            continue
        mb = _BEGIN_RE.match(ln)
        if mb and not literal_prefixes[i]:
            flush(lineno - 1)
            env = mb.group(1)
            end = _env_end_line(lines, i, env, known_macros, masked_lines=masked_lines)
            body_lines = lines[i:end + 1]
            body = "\n".join(body_lines)
            labels = _LABEL_ANY_RE.findall(_masked_tex_comments(body, known_macros))
            body_info = _environment_body(body, env, known_macros=known_macros)
            declared_kind = declared_envs.get(env, "")
            readable_env = (env in {"abstract", "quote", "quotation", "acknowledgments", "acknowledgements"}
                            or env in _MATH_ENVS or env in {"gathered", "aligned", "split", "cases"}
                            or env in _FIGURE_ENVS or env in _LIST_ENVS or env in _THEOREM_ENVS
                            or env in _READABLE_WRAPPERS or env in _TABLE_ENVS or env == "widetext"
                            or bool(declared_kind))
            if body_info is None:
                cap_tex, cap_lo, cap_hi, cap_off = _caption_of(lines, i, end, known_macros)
                extra = {"env": env, "labels": labels,
                         "reason": f"the unbalanced {env} environment is shown as source"}
                if cap_lo:
                    extra.update(caption=cap_tex,
                                 caption_pieces=tex_pieces(cap_tex, known_macros, base=cap_off),
                                 caption_src={"file": file_rel, "repo_file": repo_file,
                                              "line_start": cap_lo, "line_end": cap_hi})
                emit("raw", lineno, end + 1, **extra)
                i = end + 1
                continue
            if env in {"abstract", "quote", "quotation", "acknowledgments", "acknowledgements"}:
                inner, inner_base, _ = body_info
                emit("para", lineno, end + 1, env=env, labels=labels,
                     pieces=tex_pieces(inner, known_macros, base=inner_base))
                i = end + 1
                continue
            if env == "widetext":
                # revtex's two-column escape is an INERT WRAPPER, almost always around
                # one display equation; typing the wrapper itself made every such
                # equation an opaque raw block (measured: 34 of subset-sum-itqde's 39
                # raws). Look through it: the wrapped math env classifies on its own
                # terms, and the block's span keeps the WHOLE wrapper so a rewrite's
                # byte guard still covers exactly what is on disk.
                inner_env = None
                wrapped, _wrapped_base, _ = body_info
                wrapped = wrapped.strip()
                if wrapped.startswith(r"\[") and wrapped.endswith(r"\]"):
                    emit("equation", lineno, end + 1, env="displaymath",
                         math=_LABEL_ANY_RE.sub("", wrapped[2:-2].strip()),
                         labels=labels, number=None)
                    i = end + 1
                    continue
                for j in range(i + 1, end):
                    st = lines[j].strip()
                    if not st:
                        continue
                    if literal_prefixes[j]:
                        break
                    mi = _BEGIN_RE.match(st)
                    if mi and mi.group(1) in _MATH_ENVS:
                        inner_env = mi.group(1)
                        inner_end = _env_end_line(lines, j, inner_env, known_macros,
                                                  masked_lines=masked_lines)
                        inner = "\n".join(lines[j + 1:inner_end])
                        emit("equation", lineno, end + 1, env=inner_env,
                             math=_LABEL_ANY_RE.sub("", inner),
                             labels=labels, number=None)
                    break
                if inner_env is not None:
                    i = end + 1
                    continue
            if env in _MATH_ENVS or env in {"gathered", "aligned", "split", "cases"}:
                inner, _inner_base, _ = body_info
                math, equation_labels = _equation_math(inner)
                emit("equation", lineno, end + 1, env=env, math=math,
                     labels=labels, equation_labels=equation_labels, number=None)
            elif env in _FIGURE_ENVS:
                images: list[dict] = []
                for mg in _INCLUDEGRAPHICS_RE.finditer(body):
                    arg, _ = _brace_arg(body, mg.end() - 1)
                    p, rel = _resolve_image(md, arg, troot)
                    images.append({"arg": arg, "file": rel, "exists": p is not None,
                                   "route": _asset_route(corpus, dir_param, rel)
                                   if p is not None else ""})
                cap_tex, cap_lo, cap_hi, cap_off = _caption_of(lines, i, end, known_macros)
                extra: dict[str, Any] = {
                    "env": env, "labels": labels,
                    "label": next((l for l in labels if l.startswith("fig:")),
                                  labels[0] if labels else ""),
                    "images": images,
                    "image": images[0]["route"] if images else "",
                    "caption": cap_tex,
                    "caption_pieces": tex_pieces(cap_tex, known_macros, base=cap_off),
                }
                if cap_lo:
                    extra["caption_src"] = {"file": file_rel, "repo_file": repo_file,
                                            "line_start": cap_lo, "line_end": cap_hi}
                    extra['caption_separate'] = True
                emit("figure", lineno, end + 1, **extra)
                if cap_lo:
                    # Captions have their own exact source-addressed edit surface.
                    # Their command/braces stay in tex; only the authored body is
                    # projected as prose, so edits cannot consume the figure code.
                    caption_base = sum(len(line) + 1 for line in lines[i:cap_lo - 1])
                    emit('caption', cap_lo, cap_hi,
                         pieces=tex_pieces(cap_tex, known_macros, base=cap_off - caption_base),
                         figure_label=extra['label'], labels=[], caption_of=out[-1]['id'])
            elif env == "thebibliography":
                inner, base, _ = body_info
                items = bibliography_items(inner, known_macros, base)
                lead = len(inner) - len(inner.lstrip())
                _width, past_width = _brace_arg(inner, lead)
                empty = past_width != lead and not _flatten_pieces(tex_pieces(inner[past_width:], known_macros)).strip()
                if items or empty:
                    emit("list", lineno, end + 1, env=env, title="References",
                         ordered=False, labels=labels, items=items)
                else:
                    emit("raw", lineno, end + 1, env=env, labels=labels,
                         reason="The bibliography has no readable bibitem entries; inspect its exact source.")
            elif env in _LIST_ENVS:
                # the block's tex opens on the \begin line, so an item's offsets are
                # shifted by exactly that first line (plus its newline) — the piece
                # offsets an item carries address the BLOCK's tex, like every other piece.
                inner, base, _ = body_info
                lead = len(inner) - len(inner.lstrip())
                _options, past = _opt_arg(inner, lead)
                if past != lead:
                    inner, base = inner[past:], base + past
                emit("list", lineno, end + 1, env=env,
                     ordered=env == "enumerate", labels=labels,
                     items=list_items(inner, known_macros, base=base))
            elif env in _THEOREM_ENVS or declared_kind == "theorem":
                inner, inner_base, _ = body_info
                lead = len(inner) - len(inner.lstrip())
                optional_text, past = _opt_arg(inner, lead)
                if past != lead:
                    inner, inner_base = inner[past:], inner_base + past
                presentation = declared_presentation.get(env, {})
                display_name = _flatten_pieces(tex_pieces(
                    presentation.get("theorem_label") or env.capitalize(), known_macros))
                # amsthm proof's optional argument replaces its name; newtheorem
                # optional arguments are authored subtitles beside the declared name.
                named = declared_kind == "theorem" or env != "proof"
                emit("theorem", lineno, end + 1, env=env, labels=labels,
                     title=optional_text or display_name,
                     theorem_label=display_name if named else "",
                     theorem_optional_title=bool(optional_text) and named,
                     theorem_numbered=presentation.get("numbered") != "false" and named,
                     number_labels=_environment_number_labels(inner, known_macros),
                     title_pieces=tex_pieces(optional_text, known_macros,
                                            base=body_info[1] + lead + 1) if optional_text else [],
                     pieces=tex_pieces(inner, known_macros, base=inner_base))
            elif env in _TABLE_ENVS or (env == "center" and re.search(
                    r"\\begin\s*\{(?:tabular\*?|longtable|table\*?|ruledtabular)\}",
                    _masked_tex_comments(body, known_macros))):
                rows = _table_payload(body, env, known_macros)
                cap_tex, cap_lo, cap_hi, cap_off = _caption_of(lines, i, end, known_macros)
                if rows is None:
                    extra = {"env": env, "labels": labels,
                             "reason": f"the {env} table grammar could not be parsed safely"}
                    if cap_lo:
                        extra.update(caption=cap_tex,
                                     caption_pieces=tex_pieces(cap_tex, known_macros, base=cap_off),
                                     caption_src={"file": file_rel, "repo_file": repo_file,
                                                  "line_start": cap_lo, "line_end": cap_hi})
                    emit("raw", lineno, end + 1, **extra)
                else:
                    extra = {"env": env, "labels": labels, "rows": rows,
                             "caption": cap_tex,
                             "caption_pieces": tex_pieces(cap_tex, known_macros, base=cap_off)}
                    if cap_lo:
                        extra["caption_src"] = {"file": file_rel, "repo_file": repo_file,
                                                "line_start": cap_lo, "line_end": cap_hi}
                    emit("table", lineno, end + 1, **extra)
            elif env in _READABLE_WRAPPERS:
                inner, inner_base, _ = body_info
                title = "Explanation" if env in {"explained", "explanation"} else env.replace("the", "").capitalize()
                title_pieces = []
                if env in {"explained", "explanation"}:
                    lead = len(inner) - len(inner.lstrip())
                    title, past = _brace_arg(inner, lead)
                    if past != lead:
                        title_pieces = tex_pieces(title, known_macros, base=inner_base + lead + 1)
                        inner, inner_base = inner[past:], inner_base + past
                    else:
                        title = "Explanation"
                elif env == "algorithm":
                    lead = len(inner) - len(inner.lstrip())
                    _options, past = _opt_arg(inner, lead)
                    if past != lead:
                        inner, inner_base = inner[past:], inner_base + past
                    caption, _, _, cap_offset = _caption_of(lines, i, end, known_macros)
                    if caption:
                        title, title_pieces = caption, tex_pieces(caption, known_macros, base=cap_offset)
                        cm = _CAPTION_RE.search(inner)
                        if cm:
                            _, past_caption = _brace_arg(inner, cm.end() - 1)
                            # Keep length/offsets intact when removing the title's second copy.
                            inner = inner[:cm.start()] + " " * (past_caption - cm.start()) + inner[past_caption:]
                emit("theorem", lineno, end + 1, env=env, labels=labels,
                     title=title, title_pieces=title_pieces,
                     pieces=tex_pieces(inner, known_macros, base=inner_base))
            elif declared_kind:
                # The declaration was found in this selected manuscript's own
                # preamble.  The body remains source-mapped prose; a tcolorbox also
                # receives a compiler preview later in doc(), using that same preamble.
                inner, inner_base, _ = body_info
                lead = len(inner) - len(inner.lstrip())
                title, past = _brace_arg(inner, lead)
                title_pieces = []
                if past != lead:
                    title_pieces = tex_pieces(title, known_macros, base=inner_base + lead + 1)
                    inner, inner_base = inner[past:], inner_base + past
                chrome_template = (declared_presentation.get(env, {}).get("title_template")
                                   if declared_presentation else "")
                title_prefix, title_suffix = _title_chrome(chrome_template, known_macros)
                extra = {"env": env, "custom_kind": declared_kind, "labels": labels,
                         "title": title or env.replace("@", " ").capitalize(),
                         "title_pieces": title_pieces,
                         "pieces": tex_pieces(inner, known_macros, base=inner_base)}
                if title_prefix or title_suffix:
                    extra.update(title_prefix=title_prefix, title_suffix=title_suffix)
                emit("custom", lineno, end + 1, **extra)
            else:
                # A balanced environment may come from the document class or an
                # installed package rather than a local declaration we can parse.
                # Keep its source span and let the existing no-shell-escape TeX
                # preview decide whether the actual preamble defines it.
                inner, inner_base, _ = body_info
                emit("custom", lineno, end + 1, env=env, custom_kind="compiled",
                     labels=labels, title=env.replace("@", " ").capitalize(),
                     title_pieces=[], pieces=tex_pieces(inner, known_macros, base=inner_base))
            i = end + 1
            continue
        if buf_start == 0:
            buf_start = lineno
        i += 1
    flush(n)
    return out


_CAPTION_RE = re.compile(r"\\caption\s*(?:\[[^\]]*\])?\s*\{")


def _caption_of(lines: list[str], lo: int, hi: int, known_macros=frozenset()) -> tuple[str, int, int, int]:
    """The ``\\caption{…}`` inside a float's line range: ``(caption tex, start line, end
    line, char offset)``, lines 1-based inclusive, or ``("", 0, 0, 0)``. The caption is the
    block the author redlines most on a figure, so it carries its own source span.

    The char offset is where the caption's CONTENT begins inside the block's own ``tex``
    (``"\\n".join(lines[lo:hi+1])`` is exactly that string), so the caption's pieces carry
    offsets addressing the block's tex like every other piece."""
    body = "\n".join(lines[lo:hi + 1])
    m = _CAPTION_RE.search(_masked_tex_comments(body, known_macros))
    if m is None:
        return "", 0, 0, 0
    opening = m.end() - 1
    cap, endidx = _brace_arg(body, opening, require_closed=True, known_macros=known_macros)
    if endidx == opening:
        # _brace_arg returns the remaining source on an unclosed group. That is
        # useful for marked fallback, but it is not an editable caption boundary.
        return "", 0, 0, 0
    start_line = lo + 1 + body.count("\n", 0, m.start())
    end_line = lo + 1 + body.count("\n", 0, endidx)
    return cap, start_line, min(end_line, hi + 1), m.end()


# ---------------------------------------------------------------------------
# GET /walk/doc — the whole document model
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r"\\title\s*(?:\[[^\]]*\])?\s*\{")

# ---------------------------------------------------------------------------
# THE ROOT'S OWN CONTENT (GAP-20260810-root-content-dropped)
#
# Prose written straight into main.tex — an acknowledgments block, a Data Availability
# section, anything the author typed between the \inputs — used to be absent from the block
# model with nothing said. A silent hole in a canvas whose whole claim is content fidelity.
#
# The fix is one mask and no new parser: every root line that is NOT content is blanked to
# an empty line, so the line NUMBERS still address main.tex exactly, and `blocks_for` runs
# over the result unchanged. What was blanked is named in a one-line note on the payload —
# the honest half of "no silent holes": either it renders, or the payload says it did not.
# ---------------------------------------------------------------------------

#: root lines that are TYPESET PLUMBING, not prose a reader redlines. Each one is a whole
#: line's own command; nothing here can swallow a paragraph.
_PLUMBING_RE = re.compile(
    r"^\s*\\(maketitle|tableofcontents|listoffigures|listoftables|appendix|clearpage|"
    r"newpage|pagebreak|frontmatter|mainmatter|backmatter|cleardoublepage|onecolumn|twocolumn|bibliographystyle|bibliography|"
    r"printbibliography|addbibresource|title|author|affiliation|altaffiliation|date|"
    r"thanks|email|homepage|pacs|keywords|preprint|collaboration|noaffiliation|"
    r"newcommand|renewcommand|providecommand|def|setcounter|graphicspath|noindent)\b")


def _plumbing_only(line: str, match: re.Match) -> bool:
    """A command prefix does not grant permission to discard trailing prose."""
    zero = {"maketitle", "tableofcontents", "listoffigures", "listoftables", "appendix",
            "clearpage", "newpage", "pagebreak", "onecolumn", "twocolumn", "noindent",
            "noaffiliation", "frontmatter", "mainmatter", "backmatter", "cleardoublepage"}
    cursor = match.end()
    if match.group(1) not in zero:
        while cursor < len(line):
            while cursor < len(line) and line[cursor].isspace():
                cursor += 1
            if cursor < len(line) and line[cursor] in "{[":
                opener = line[cursor]
                _, end = (_brace_arg if opener == "{" else _opt_arg)(line, cursor)
                if end <= cursor or line[end - 1] != ("}" if opener == "{" else "]"):
                    return False
                cursor = end
            else:
                break
    remainder = line[cursor:].strip()
    return not remainder or remainder.startswith("%")


def root_content(root_text: str, known_macros=frozenset()) -> tuple[str, list[str]]:
    """The root's own CONTENT, line-for-line: ``(masked_text, skipped)``.

    ``masked_text`` is ``root_text`` with every non-content line replaced by an EMPTY line
    — same line count, same line numbers, so a block cut from it addresses ``main.tex``
    exactly. ``skipped`` names what was blanked, in the words the payload's note prints.

    Three passes, in order: the preamble and everything from ``\\end{document}``; the
    ``\\input`` lines (they are rendered as their own files, in their own place) and the
    plumbing commands; and finally any environment whose body became EMPTY once its
    ``\\input`` was blanked — a revtex ``abstract`` wrapping ``\\input{abstract}`` is the
    case that matters, and leaving its two bare lines behind would print an empty raw
    block where the abstract fragment already renders."""
    lines = root_text.split("\n")
    masked_lines, literal_prefixes = _structural_pass(root_text, lines, known_macros)
    out = list(lines)
    skipped: list[str] = []
    n = len(lines)
    begin = next((i for i, ln in enumerate(masked_lines)
                  if not literal_prefixes[i] and re.match(r"^\s*\\begin\s*\{document\}", ln)), -1)
    end = next((i for i in range(n - 1, -1, -1)
                if not literal_prefixes[i] and re.match(r"^\s*\\end\s*\{document\}", masked_lines[i])), n)
    if begin >= 0:
        for i in range(0, begin + 1):
            out[i] = ""
        skipped.append("the preamble")
    for i in range(min(end, n), n):
        out[i] = ""
    seen: set[str] = set()
    for i in range(max(begin + 1, 0), min(end, n)):
        ln = lines[i]
        if literal_prefixes[i]:
            continue
        if _INPUT_LINE_RE.match(ln):
            out[i] = ""                    # rendered as its own file, in its own place
            continue
        mp = _PLUMBING_RE.match(ln)
        if mp and _plumbing_only(ln, mp):
            out[i] = ""
            if mp.group(1) not in seen:
                seen.add(mp.group(1))
                skipped.append("\\" + mp.group(1))
    for i in range(max(begin + 1, 0), min(end, n)):
        mb = _BEGIN_RE.match(out[i])
        if mb is None or literal_prefixes[i]:
            continue
        env = mb.group(1)
        stop = _env_end_line(out, i, env, known_macros, masked_lines=masked_lines)
        # A complete environment can open and close on one source line.  Testing
        # only the intervening *lines* makes that real body look empty and drops
        # it as an include wrapper.  Ask the same balanced-body parser used by
        # block construction instead.
        body_info = _environment_body("\n".join(out[i:stop + 1]), env, known_macros=known_macros)
        if body_info is not None and body_info[0].strip():
            continue                       # it holds real content: it stays
        for j in range(i, stop + 1):
            out[j] = ""
        if env not in seen:
            seen.add(env)
            skipped.append(f"the {env} wrapper (its text is its own \\input fragment)")
    return "\n".join(out), skipped


#: the ONE producer of the root's ``\input`` order is ``projection_viewer._INPUT_RE``; this
#: is the same pattern anchored to a whole line, used only to BLANK those lines in the mask.
_INPUT_LINE_RE = re.compile(r"^\s*\\(?:input|include)\{([^}]+)\}")


def _md_rel(md: Path, p: Path) -> str:
    try:
        return p.resolve().relative_to(md.resolve()).as_posix()
    except (ValueError, OSError):
        return p.name


def doc(corpus: str = "", dir_param: str = "", identities: bool = False, *,
        known_revision: str = "", sections: list[str] | None = None,
        files: list[str] | None = None) -> dict[str, Any]:
    """The block model — the content-faithful document both legs build to.

    Scoped and conditional reads (G14):
      ``known_revision``  the ``current_revision`` the caller already holds. When the
                          document owner's revision still equals it, the answer is
                          ``{ok, unchanged: true, current_revision, source_observation,
                          presentation_revision}`` and no block model is built. It is a
                          whole-document condition: combined with ``sections``/``files``
                          it is ignored (``known_revision_ignored: true``) and the selected
                          sections are delivered, because the whole-document revision does
                          not say which sections the caller already holds.
      ``sections``        section ids; ``files`` manuscript-relative source files. Either
                          selects the sections to deliver: the answer keeps every
                          document-level field (macros, citations, refs, revisions) and
                          ``sections`` holds only the selected ones, with
                          ``partial: true``, ``selected_sections`` and ``section_index``
                          (id, title, file, blocks, file_revision for EVERY section) so a
                          consumer can tell a structure change from a content change.
    The grain is the SECTION: it is the unit the walk adopts and the unit a saved
    edit touches. Building the model still parses the whole traversal (one parse
    per read; a per-file parse cache is not part of this cut), so a scoped read
    saves bytes and client adoption work, not server parsing; a conditional read
    saves both.

    ``{ok, corpus, title, macros, citations, refs, sections:[{id,title,file,blocks:[…]}]}``
    (plus ``root``, ``ref_pages``, ``counts`` and the plain ``fidelity`` sentence).

    Built on the EXISTING machinery, one producer throughout: the file order comes from
    ``projection_viewer.doc_model`` (the root's ``\\input`` order), the paragraph grain from
    ``projection_viewer.parse_paragraphs``, the manuscript dir from
    ``review_surface.manuscript_dir``. Nothing here re-derives what those already know.

    Every ``src`` path is MANUSCRIPT-relative, because that is the vocabulary the rewrite
    door consumes (``review_surface._fragment_path``) — one addressing scheme from the
    canvas to the splice. The repo-relative twin rides alongside as ``repo_file``."""
    from laplace.manuscript import projection_viewer as pv
    from laplace.manuscript import review_surface as rv
    # The selectors keep their own names: the body below builds the local `sections` list.
    sections_selector = [str(item) for item in (sections or []) if item]
    files_selector = [str(item) for item in (files or []) if item]

    md = rv.manuscript_dir(corpus, dir_param)
    if md is None:
        return {"ok": False, "error": "unknown corpus / dir",
                "note": "the walk reads a project the registry resolves; name one with "
                        "?corpus= or point at a manuscript directory with ?dir="}
    root_tex = md / "main.tex"
    source_resolution: dict[str, Any] | None = None
    if corpus:
        source_resolution = manuscript_source.resolve(corpus, repo_root=_repo_root())
        # The shared resolver is the source authority for every project.  A
        # registered source is not merely an atomiser input: it is the fallback
        # when the old target is absent or an empty scaffold.  Ambiguity stays
        # visible below; it is never resolved by a local walk heuristic.
        if (source_resolution.get("status") in {"resolved", "empty"}
                and source_resolution.get("root")):
            root_tex = _repo_root() / str(source_resolution["root"])
            md = root_tex.parent
        elif source_resolution.get("status") == "ambiguous":
            return {"ok": False, "status": "ambiguous-source", "source": source_resolution,
                    "source_status": source_resolution.get("status"),
                    "source_revision": source_resolution.get("revision"),
                    "source_candidates": source_resolution.get("candidates", []),
                    "error": "more than one manuscript edition is viable; choose one in the project manifest"}
    if not root_tex.is_file():
        return {"ok": False, "error": f"no main.tex in {_md_rel(md, md)}",
                "note": "the block model is built from the root tex and the files it "
                        "\\inputs; without a root there is no document order to follow"}
    root_text = root_tex.read_text(encoding="utf-8", errors="replace")
    title = ""
    mt = _TITLE_RE.search(root_text)
    if mt is not None:
        title_tex, _ = _brace_arg(root_text, mt.end() - 1)
        title = _flatten_pieces(tex_pieces(title_tex))

    macros = preamble_macros(root_tex)
    from laplace.manuscript import manuscript_figure_preview
    declared_envs = manuscript_figure_preview.declared_environments(root_tex, _repo_root().resolve())
    declared_presentation = manuscript_figure_preview.declared_environment_presentation(
        root_tex, _repo_root().resolve())
    known = macros

    bbl = _resolve_bib_artifact(md, corpus, "main.bbl", root_tex)
    citations = parse_bbl(bbl.read_text(encoding="utf-8", errors="replace")) \
        if bbl is not None else {}
    aux = _resolve_bib_artifact(md, corpus, "main.aux", root_tex)
    aux_text = aux.read_text(encoding="utf-8", errors="replace") if aux is not None else ""
    refs, ref_pages = parse_aux(aux_text)

    repo_root = _repo_root().resolve()
    try:
        root_rel = root_tex.resolve().relative_to(repo_root).as_posix()
    except (ValueError, OSError):
        root_rel = str(root_tex)
    source_tree = manuscript_source.traversal(root_tex, repo_root=repo_root)
    if known_revision and (sections_selector or files_selector):
        # The whole-document revision says nothing about which sections a caller holds, so a
        # scoped read is never conditional: the selected sections are delivered and the
        # ignored condition is stated.
        known_revision = ""
        known_revision_ignored = True
    else:
        known_revision_ignored = False
    if known_revision and corpus and source_resolution:
        # G14 conditional read: the document owner's revision is the identity the
        # poller holds; equal means nothing to deliver and nothing to parse.
        from laplace.manuscript import document
        current = document.current(rv._project_name(corpus, md), repo_root, source=source_resolution,
                                   source_tree=source_tree, include_preview=False)
        if current["current_revision"] == known_revision:
            return {"ok": True, "unchanged": True, "corpus": corpus, "dir": dir_param,
                    **{key: current[key] for key in ("project", "source_observation", "presentation_revision", "current_revision")}}
    for key, row in inline_citations(source_tree, parse_aux_citations(aux_text)).items():
        citations.setdefault(key, row)
    citation_target_rows = citation_targets(root_tex, md, source_tree, citations)

    sections: list[dict[str, Any]] = []
    missing: list[str] = []
    cur: dict[str, Any] | None = None

    def open_front(file_rel: str) -> dict[str, Any]:
        nonlocal cur
        cur = {"id": "front", "title": "Front matter", "file": file_rel,
               "label": "", "blocks": []}
        sections.append(cur)
        return cur

    def place(blk: dict, file_rel: str) -> None:
        """One block into the section it belongs to, opening a new section on a section
        head and Front matter before the first one. ONE placer for the root's own blocks
        and the fragments' alike — the root used to have no path here at all."""
        nonlocal cur
        if blk["kind"] == "head" and blk.get("level") in {"part", "chapter", "section"}:
            cur = {"id": blk.get("label") or _slug(blk.get("title") or ""),
                   "title": blk.get("title") or "",
                   "file": file_rel, "label": blk.get("label") or "",
                   "depth": {"part": 0, "chapter": 1, "section": 2}.get(blk.get("level"), 2),
                   "blocks": []}
            sections.append(cur)
        if cur is None:
            cur = open_front(file_rel)
        cur["blocks"].append(blk)
        if blk["kind"] == "equation" or (blk["kind"] == "theorem" and blk.get("theorem_numbered")):
            for lab in (blk.get("number_labels") if blk["kind"] == "theorem" else blk.get("labels")) or []:
                if lab in refs:
                    blk["number"] = refs[lab]
                    break

    # THE ROOT'S OWN CONTENT, IN ITS OWN PLACE (GAP-20260810-root-content-dropped).
    # The root is masked to its content lines (`root_content`), cut into blocks by the
    # same `blocks_for` every fragment rides, and then MERGED with the \input entries BY
    # LINE NUMBER — so an acknowledgments block written at line 77 lands after the section
    # \input on line 75 and before the appendix \input on line 94, which is where it is
    # typeset. No new ordering authority: main.tex's own line order is the authority.
    root_rel_md = _md_rel(md, root_tex)
    skipped: list[str] = []
    root_blocks: list[dict] = []
    children: dict[str, list[dict]] = {}
    for instance in source_tree.get("sources", [])[1:]:
        parent = instance.get("parent")
        if isinstance(parent, str):
            children.setdefault(parent, []).append(instance)

    def _fragment_mask(text: str) -> str:
        """Blank include calls without changing source line addresses."""
        lines = text.split("\n")
        return "\n".join("" if pv._INPUT_RE.match(line) else line for line in lines)

    def render_instance(instance: dict, is_root: bool = False) -> None:
        nonlocal skipped, root_blocks
        text = str(instance.get("text") or "")
        repo_file = str(instance.get("file") or "")
        fp = repo_root / repo_file
        file_rel = _md_rel(md, fp)
        masked = _fragment_mask(text)
        if is_root:
            masked, skipped = root_content(text, known)
        blocks = blocks_for(masked, file_rel=file_rel, repo_file=repo_file, md=md,
                            corpus=corpus, dir_param=dir_param,
                            para_spans=pv.parse_paragraphs(masked), known_macros=known,
                            declared_envs=declared_envs,
                            declared_presentation=declared_presentation)
        for block in blocks:
            if block.get("kind") == "custom":
                block["presentation"] = {key: value for key, value in
                                         declared_presentation.get(block.get("env"), {}).items()
                                         if key != "title_template"}
        if is_root:
            root_blocks = blocks
        events: list[tuple[int, int, Any]] = [
            (int(block["src"]["line_start"]), 0, block) for block in blocks]
        uncommented = manuscript_source._uncomment(text)
        body_begin = re.search(r"\\begin\s*\{document\}", uncommented) if is_root else None
        body_end = re.search(r"\\end\s*\{document\}", uncommented) if is_root else None
        first_body_line = uncommented[:body_begin.end()].count('\n') + 1 if body_begin else 0
        last_body_line = uncommented[:body_end.start()].count('\n') + 1 if body_end else len(text.splitlines()) + 1
        events += [(int(child.get("include_line") or 0), 1, child)
                   for child in children.get(repo_file, [])
                   if not is_root or first_body_line <= int(child.get('include_line') or 0) <= last_body_line]
        for _line, kind, item in sorted(events, key=lambda value: (value[0], value[1])):
            if kind == 0:
                place(item, file_rel)
            else:
                render_instance(item)

    if source_tree.get("sources"):
        render_instance(source_tree["sources"][0], is_root=True)
    # Resolve declared images independently of an imported project's research
    # state directory, and route only the exact dependencies declared here.
    if corpus and not dir_param:
        from laplace.manuscript import tex_dependencies
        from urllib.parse import urlencode
        graphics = {(row['source'], row['argument']): row
                    for row in tex_dependencies.graphic_references(root_tex, repo_root)}
        source_digests = {item['file']: item['sha256'] for item in source_tree.get('sources', [])}
        for section in sections:
            for block in section['blocks']:
                if block.get('kind') not in {'figure', 'custom'}:
                    continue
                custom_environment = (block.get('env') if block.get('kind') == 'custom'
                                      and block.get('custom_kind') in {'tcolorbox', 'compiled'} else '')
                if block.get('kind') == 'custom' and not custom_environment:
                    continue
                for image in block.get('images') or []:
                    declared = graphics.get((block['src']['repo_file'], image['arg']))
                    if declared and declared['status'] == 'AVAILABLE':
                        import hashlib
                        asset_version = hashlib.sha256((repo_root / declared['repo_file']).read_bytes()).hexdigest()
                        image.update(exists=True, file=declared['repo_file'],
                                     route='/walk/asset?' + urlencode({'corpus': corpus,
                                                                      'repo_file': declared['repo_file'],
                                                                      'v': asset_version}))
                        if Path(declared['repo_file']).suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif'}:
                            try:
                                from PIL import Image
                                with Image.open(repo_root / declared['repo_file']) as raster:
                                    image['width'], image['height'] = raster.size
                            except (ImportError, OSError, ValueError):
                                pass
                block['image'] = next((item['route'] for item in block.get('images') or []
                                       if item.get('route')), '')
                previewable = (manuscript_figure_preview.supports(block.get('tex') or '')
                               if not custom_environment else True)
                if previewable:
                    block['image'] = '/walk/figure-preview?' + urlencode({
                        'corpus': corpus, 'file': block['src']['repo_file'],
                        'line_start': block['src']['line_start'], 'line_end': block['src']['line_end'],
                        'source_revision': (source_resolution or {}).get('revision'),
                        'source_file_revision': source_digests.get(block['src']['repo_file']),
                        'format': 'png', **({'environment': custom_environment} if custom_environment else {})})
                    block['preview_kind'] = ('declared-custom-environment' if custom_environment
                                             else 'authored-inline-figure')
                    block['preview_image'] = block['image']
    missing = [str(record.get("target") or record.get("argument") or "")
               for record in source_tree.get("includes", []) if not record.get("exists")]

    n_blocks = sum(len(s["blocks"]) for s in sections)
    if n_blocks == 0:
        return {"ok": False, "status": "empty-source", "source": source_resolution,
                "root": root_rel, "manuscript_dir": _md_rel(_repo_root().resolve(), md),
                "source_status": (source_resolution or {}).get("status"),
                "source_revision": (source_resolution or {}).get("revision"),
                "source_candidates": (source_resolution or {}).get("candidates", []),
                "source_diagnostics": source_tree.get("diagnostics", []),
                "error": "the selected manuscript source has no renderable blocks"}
    # ── THE IDENTITIES THE CANVAS PUBLISHES (WRITING-CONSOLIDATION-W1) ──────────────────
    # Every editable block carries `expected`: the `prose` token of its own addressed span,
    # in the exact field the request takes, so the editor SENDS a token it read and derives
    # nothing. Three properties, each load-bearing:
    #   * the bytes are `blk["tex"]`, which IS `"\n".join(lines[lo-1:hi])` (:1832) --- the
    #     same string `review_surface.adjudicate` reads back out of the file at :1890, so the
    #     canvas and the door cannot disagree about what was digested;
    #   * one sha256 per block over bytes already in hand: no second file read, and the token
    #     is `grammar.digest_bytes`, the owner's own function, never a new digest scheme;
    #   * it is a LIST because `expected` is a list (GRAMMAR.md section 5), so the editor's
    #     send is a copy rather than a construction.
    # A dir-only walk has no project name, and the grammar's `::<id>` form is the home id for
    # a home that is not per project, so the token is still well-formed and still parses.
    #
    # IT IS A PARAMETER, AND THE WALK'S CANVAS ALWAYS SETS IT. Measured on the author's own
    # manuscript (1,271 blocks, 4 fragment files, median of five runs each): 1,466,581 bytes with
    # the flag off against 1,661,568 with it on --- +194,987 bytes, +13.3 per cent --- and
    # the TIME is below the noise floor of this measurement: two medians of five runs each gave
    # 181.0 against 183.1 ms and then 204.5 against 190.0 ms, so what this costs is bytes, not
    # latency. The editor needs a token on every block because any block may be
    # the next one he types in, and the walk is ALSO how he reads: there is no read-only canvas,
    # so every walk load pays this, and the honest statement of the cost is the measurement, not
    # the word "asked for". What is true is narrower: the OTHER callers of this door --- the PDF
    # leg, the front carrier, a host handing in a document --- do not set the flag and pay
    # nothing. Whether a reader should pay 13 per cent for an editor's token is the measure and
    # storage lanes' call against guarantees B and C; this packet reports it as a residual.
    doc_project = rv._project_name(corpus, md)
    _files: list[str] = []
    for _sec in (sections if identities else ()):
        for _blk in _sec.get("blocks", ()):
            _s = _blk.get("src") or {}
            if not _s.get("file") or not _s.get("line_start"):
                continue
            if _s["file"] not in _files:
                _files.append(str(_s["file"]))
            _blk["expected"] = [str(g.mint(
                "prose", "%s::%s:%d-%d" % (doc_project, _s["file"], int(_s["line_start"]),
                                           int(_s["line_end"] or _s["line_start"])),
                g.digest_bytes(str(_blk.get("tex") or "").encode("utf-8"))))]
    # THE CONTAINER'S IDENTITY, FOR THE TWO ALTITUDES WHOSE CONTAINER IS THE FILE
    # (WRITING-CONSOLIDATION-W1, continuation 1). A `create note@section` or `note@chapter` gate
    # proves the FILE's bytes (`identity_doors.COMMENT_CONTAINER`), and the canvas had no file
    # token at all --- so the editor could send one at paragraph altitude and nothing at the
    # other two, and a section ruling banked against bytes the author may never have read.
    #
    # IT IS PUBLISHED BY THE READ THE PAGE IS BUILT FROM, not by a second read at the moment of
    # banking: a token read beside the gate is current by construction and could never refuse
    # anything. These are the identities of the bytes this answer RENDERS, so a file another
    # writer moves afterwards is refused with `needed`.
    #
    # The home id is `_fragment_rel`'s spelling --- manuscript-relative posix, which is the same
    # `src.file` the blocks carry and the same path the comment door resolves through
    # `_fragment_path(md, section, file)` --- so the token the canvas sends is the token the gate
    # mints. One read per FILE (~50 for his manuscript, against 1,241 blocks), both home kinds
    # over the same bytes because the grammar declares both over one source file and a request
    # carries exactly one of them.
    doc_identities: dict[str, str] = {}
    for _rel in _files:
        try:
            _raw = (md / _rel).resolve().read_bytes()
        except OSError:
            continue                      # a fragment the walk listed and the disk does not hold
        doc_identities.update(identity_doors.identities(
            ("section", "%s::%s" % (doc_project, _rel), _raw),
            ("chapter", "%s::%s" % (doc_project, _rel), _raw)))
    file_revisions = {_md_rel(md, repo_root / item['file']): item['sha256']
                      for item in source_tree.get('sources', [])}
    # Every section's place and source identity, whatever subset is delivered below.
    section_index = [{"id": section["id"], "file": section.get("file", ""),
                      "blocks": len(section["blocks"]), "file_revision": file_revisions.get(section.get("file", ""))}
                     for section in sections]
    wanted_sections = set(sections_selector or [])
    wanted_files = set(files_selector or [])
    delivered = ([section for section in sections
                  if section["id"] in wanted_sections or section.get("file") in wanted_files]
                 if (wanted_sections or wanted_files) else sections)
    out: dict[str, Any] = {
        "ok": True, "corpus": corpus, "dir": dir_param,
        # one name per value, keyed by the home, for every fragment file (see above). Absent
        # unless `identities` was asked for, exactly like the per-block tokens.
        **({"identities": doc_identities} if identities and doc_identities else {}),
        "title": title, "root": root_rel,
        "source": source_resolution,
        "source_status": (source_resolution or {}).get("status", "legacy"),
        "source_revision": (source_resolution or {}).get("revision"),
        "source_file_revisions": file_revisions,
        "section_index": section_index,
        **({"partial": True, "selected_sections": [section["id"] for section in delivered],
            **({"known_revision_ignored": True} if known_revision_ignored else {})}
           if (wanted_sections or wanted_files) else {}),
        "source_candidates": (source_resolution or {}).get("candidates", []),
        "source_diagnostics": source_tree.get("diagnostics", []),
        "manuscript_dir": _md_rel(_repo_root().resolve(), md) if md else "",
        "macros": macros, "citations": citations, "citation_targets": citation_target_rows,
        "refs": refs, "ref_pages": ref_pages,
        "sections": delivered,
        "counts": {"sections": len(sections), "blocks": n_blocks,
                   "root_blocks": len(root_blocks),
                   "citations": len(citations), "citation_targets": len(citation_target_rows), "refs": len(refs),
                   "macros": len(macros)},
        "fidelity": _FIDELITY,
        # NO SILENT HOLES. Either the root's own prose renders as blocks (above, in its own
        # place by line number), or this line names what was left out and why.
        "root_note": (
            f"{root_rel_md}: {len(root_blocks)} block(s) written directly in the root "
            "render here in their own place; " + (
                "what is not rendered is " + ", ".join(skipped) + " — typeset plumbing, "
                "not prose" if skipped else "nothing in it was skipped")),
    }
    if skipped:
        out["root_skipped"] = skipped
    if doc_project and source_resolution:
        from laplace.manuscript import document
        current=document.current(doc_project,repo_root,source=source_resolution,
                                             source_tree=source_tree,include_preview=False)
        out.update({key:current[key] for key in
            ('project','source_observation','presentation_revision','current_revision','observation_coherence')})
    if doc_project and source_resolution:
        from laplace.manuscript import reader_restructure
        out['pending_restructures']=reader_restructure.annotate_walk(doc_project,repo_root,sections,source_resolution,source_tree)
    if missing:
        out["missing_files"] = missing
        out["missing_note"] = (
            f"{len(missing)} \\input file(s) named by the root are not on disk and are "
            "shown nowhere: " + ", ".join(missing))
    if not citations:
        out["citations_note"] = ("no built main.bbl anywhere the walk looks (manuscript dir, "
                                 "registry tex_root, versioned snapshots) — citation keys "
                                 "render as keys until the paper is compiled once")
    if not refs:
        out["refs_note"] = ("no built main.aux anywhere the walk looks (manuscript dir, "
                            "registry tex_root, versioned snapshots) — cross-references "
                            "render as labels until the paper is compiled once")
    return out


# ---------------------------------------------------------------------------
# GET /walk/asset — one figure's bytes, unrasterised
# ---------------------------------------------------------------------------

def asset(corpus: str, dir_param: str, file_param: str, repo_file: str = '') -> tuple[int, str, bytes]:
    """One figure asset's bytes, served with its real content type — a figure PDF goes out
    as ``application/pdf`` for the client's pdf.js, NEVER rasterised here (the server does
    not decide how the page draws a vector figure).

    Fenced inside the trust root (:func:`_trust_root`) — the manuscript directory, widened
    to the registry row's declared ``project_dir`` for a ``?corpus=`` request ONLY, never
    for a raw ``?dir=``. An absolute path, a ``..`` traversal, or any resolution landing
    outside that one root refuses with 403."""
    if repo_file:
        if not corpus or dir_param:
            return _json_resp(403, {'error': 'Declared graphics require a registered project.'})
        from laplace.manuscript import tex_dependencies
        root = _repo_root().resolve()
        selected = manuscript_source.resolve(corpus, repo_root=root)
        if selected.get('status') != 'resolved' or not selected.get('root'):
            return _json_resp(404, {'error': 'The selected manuscript is unavailable.'})
        path = (root / repo_file).resolve()
        if not path.is_relative_to(root):
            return _json_resp(403, {'error': 'Graphic path leaves the repository.'})
        permitted = {row['repo_file'] for row in tex_dependencies.graphic_references(root / selected['root'], root)
                     if row['status'] == 'AVAILABLE'}
        if path.relative_to(root).as_posix() not in permitted:
            return _json_resp(403, {'error': 'This image is not declared by the selected manuscript.'})
        try:
            return 200, _ASSET_TYPES[path.suffix.lower()], path.read_bytes()
        except (OSError, KeyError):
            return _json_resp(404, {'error': 'The declared graphic is unavailable.'})
    from laplace.manuscript import review_surface as rv
    md = rv.manuscript_dir(corpus, dir_param)
    if md is None:
        return _json_resp(404, {"error": "unknown corpus / dir"})
    rel = (file_param or "").strip()
    if not rel:
        return _json_resp(400, {"error": "file is required"})
    root = _trust_root(corpus, dir_param, md).resolve()
    try:
        p = (Path(rel) if Path(rel).is_absolute() else root / rel).resolve()
        p.relative_to(root)
    except (ValueError, OSError):
        return _json_resp(403, {"error": "the asset door serves files inside the "
                                         "declared trust root only (the manuscript "
                                         "directory, or the project directory for a "
                                         "corpus-addressed request)"})
    if not p.is_file():
        # Earlier clients use file= for the document model's repo-relative
        # handles. Retain that spelling only through the same exact allowlist.
        if corpus and not dir_param:
            candidate = (_repo_root() / rel).resolve()
            if candidate.is_file() and candidate.is_relative_to(_repo_root().resolve()):
                return asset(corpus, '', '', candidate.relative_to(_repo_root().resolve()).as_posix())
        return _json_resp(404, {"error": f"no such asset: {rel}"})
    if corpus and not dir_param:
        from laplace.manuscript import tex_dependencies
        selected = manuscript_source.resolve(corpus, repo_root=_repo_root())
        if not selected.get('root'):
            return _json_resp(404, {'error': 'The selected manuscript is unavailable.'})
        declared = {(_repo_root() / row['repo_file']).resolve()
                    for row in tex_dependencies.graphic_references(_repo_root() / selected['root'], _repo_root())
                    if row['status'] == 'AVAILABLE'}
        if p not in declared:
            return _json_resp(403, {'error': 'This image is not declared by the selected manuscript.'})
    ctype = _ASSET_TYPES.get(p.suffix.lower(), "application/octet-stream")
    try:
        return 200, ctype, p.read_bytes()
    except OSError as exc:
        return _json_resp(500, {"error": f"asset unreadable: {exc}"})


# ---------------------------------------------------------------------------
# routing
# ---------------------------------------------------------------------------

def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/walk*`` request. Returns (status, content_type, body), or ``None`` when
    the path is not ours (the scanner falls through)."""
    if path != "/walk" and not path.startswith("/walk/"):
        return None
    method = (method or "GET").upper()

    if path == "/walk" and method == "GET":
        return 200, "text/html; charset=utf-8", page_bytes(_q1(query, "corpus"))

    if path == "/walk/doc" and method == "GET":
        # `identities=1` is the editor's ask: the per-block `prose` token it sends back in
        # `expected`. Off by default, because 11.8 per cent of this payload is tokens and a
        # reader sends no request (see `doc`).
        split = lambda value: [item for item in str(value or "").split(",") if item]
        res = doc(_q1(query, "corpus"), _q1(query, "dir"),
                  identities=_q1(query, "identities") == "1",
                  known_revision=_q1(query, "known_revision"),
                  sections=split(_q1(query, "sections")), files=split(_q1(query, "files")))
        return _json_resp(200 if res.get("ok") else 404, res)

    if path == "/walk/asset" and method == "GET":
        return asset(_q1(query, "corpus"), _q1(query, "dir"), _q1(query, "file"), _q1(query, 'repo_file'))

    if path == '/walk/figure-preview':
        from laplace.manuscript import manuscript_figure_preview
        return manuscript_figure_preview.handle(path, query, method, body, repo_root=_repo_root())

    return _json_resp(405, {"error": f"{method} {path} not supported",
                            "note": "the walk serves GET /walk (the page), GET /walk/doc "
                                    "(the block model) and GET /walk/asset (a figure's "
                                    "bytes); its deposits ride /review/adjudicate"})
