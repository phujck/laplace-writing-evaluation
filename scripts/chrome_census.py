#!/usr/bin/env python3
"""THE CHROME CENSUS — the mechanical enumerator of the Laplace interface surface.

Two families, both DERIVED FROM SOURCE (never a hand-kept list), so the count is
mechanical and re-derivable, never eyeballed:

  ROUTES  — every server route. An AST scan of ``scanner.py`` for ``u.path == "..."``,
            ``u.path.startswith("...")`` and ``u.path in (...)`` across ``do_GET`` /
            ``do_POST``; PLUS every delegated module's ``handle()`` dispatch literals
            (``path == "..."`` / ``path.startswith("...")``). ``shared_ui`` strips the
            ``/shared/`` prefix into a ``name`` local, so its ``name == "..."`` branches
            are re-prefixed. Retired stubs (/navigator, /conceptric, /editor) and the
            surviving /network/* + /corpus/* data families all fall out of the same scan.

  CONTROLS — every interactive control on every authored HTML surface: ``<button>``,
            ``<a href>``, ``<select>``, any ``[onclick]``, any ``[role=button]`` — plus
            the ``data-cgroup`` control GROUPS (the W7.3 density markers, with their
            folded state + one-click disclosure trigger). Each control carries a stable
            id (surface + best attribute/label) so a verdict store can key on it. AND
            (F8, §C1) the runtime PANE layer: the W5/W6/W7 rebuilt surfaces author zero
            control markup in their *.html and render everything from ``static_shared/
            *-panes.mjs`` — those pane controls are scanned from the .mjs and folded in
            under their consuming surface (see the PANE-MODULE CONTROLS section below).

Deterministic, stdlib-only. Emits ONE JSON object to stdout::

    {"routes": [...], "controls": [...], "groups": [...], "counts": {...}}

Run::

    .venv/bin/python scripts/chrome_census.py

The verdict store (``src/laplace/pipeline/census_verdicts.json``) is the ruling layer over this
enumeration; ``tests/test_chrome_census.py`` binds the two (every enumerated item has a
verdict, no phantom verdicts, W0 kills gone, kept-wired routes answer 200).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "laplace"

# The delegated handler modules (each owns a route prefix via its handle()).
_DELEGATED = [
    "projection_viewer", "shared_ui", "storyboard", "review_surface", "review_http",   # /review/* door (review_http since 2026-10-21)
    "altitude", "analytics", "dials_surface",
    "corpus_stats", "corpus_cocited", "dashboard",   # W1: /dashboard/* (data + New Project door)
    "artefact",                                       # W2: /artefact* (the ONE artefact surface)
    "desk",                                           # W5: /desk* (THE DESK COCKPIT; guide/tutorial died)
    "pipeline_surface",                               # W6: /pipeline* (THE PIPELINE SURFACE; /dials page died)
    "assets_surface",                                 # W7: /assets* (THE ASSET SURFACE; serves assets.html)
    "evolution_surface",                              # 2026-07-20: /evolution/* (THE EVOLUTION DESK — the ratify queue's doors)
]

_HTML_LITERAL_RE = re.compile(r"""["']([A-Za-z0-9_.-]+\.html)["']""")


def _module_file(name: str) -> Path:
    """The one source file of a route-serving module named by its basename, in whichever subsystem package it lives."""
    hits = sorted(_SRC.glob("%s.py" % name)) + sorted(_SRC.glob("*/%s.py" % name))
    if len(hits) != 1:
        raise ValueError("route-serving module %r is not exactly one file under %s: %r" % (name, _SRC, hits))
    return hits[0]


def _route_serving_modules() -> list[Path]:
    """The exact module set ``scan_routes()`` reads below (scanner.py + every delegated
    handler) — the chrome universe's route-serving source. Reused here so "does some route
    serve this file" is answered from the SAME parse, never a second hand-kept list."""
    return [_module_file("scanner")] + [_module_file(m) for m in _DELEGATED]


def _served_html_names() -> set[str]:
    """Every ``*.html`` filename literal appearing in the route-serving module set — i.e. a
    file some route actually serves (a ``Path(...) / "x.html"`` ``_HTML`` constant, a
    literal passed to ``_send()``, …). A file with zero references here is not chrome any
    route reaches, however many controls it authors.

    RULING (A3, W2 judge, review_static ontology): ``review_static.html`` was the frozen
    remote-review EXPORT TEMPLATE — no route in scanner.py or any delegated module ever
    served it, so it mechanically dropped out of ``_html_surfaces()`` here rather than being
    enumerated-then-killed, and it was never a census row of any kind. It is now DELETED
    (2026-07-17): ``scripts/export_review.py`` was ported off it onto the ARTEFACT SURFACE
    (his word PV-20260717T002125Z), so the exporter no longer reads a template file — it bakes
    ``artefact.html`` + its module graph directly (proven by tests/test_review_bundle.py). Its
    absence changes nothing here; the same ontology holds for the live artefact surface.
    """
    names: set[str] = set()
    for path in _route_serving_modules():
        names.update(_HTML_LITERAL_RE.findall(path.read_text(encoding="utf-8")))
    return names


# The authored HTML surfaces are whatever *.html sits beside scanner.py AND is actually
# served by some route (see _served_html_names) — never a hand-list, so a killed surface
# simply drops out of the census next run, and a template file no route serves (A3) never
# entered the census to begin with.
def _html_surfaces() -> list[Path]:
    served = _served_html_names()
    return sorted(p for p in (_SRC / "web").glob("*.html") if p.name in served)


# ── ROUTES ──────────────────────────────────────────────────────────────────

def _str_const(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _is_path_expr(node: ast.AST, extra_names: set[str]) -> bool:
    """True when ``node`` is the request-path expression we route on: an attribute
    ``<x>.path`` (u.path / self.path), a bare Name ``path`` (the handle() param), or one
    of the module-local aliases (shared_ui strips ``/shared/`` into ``name``)."""
    if isinstance(node, ast.Attribute) and node.attr == "path":
        return True
    if isinstance(node, ast.Name) and node.id in ({"path"} | extra_names):
        return True
    return False


class _RouteScan(ast.NodeVisitor):
    """Collects every string literal compared against the request path in one module."""

    def __init__(self, prefix: str, extra_names: set[str]) -> None:
        self.prefix = prefix                       # "" for scanner; "/shared/" for shared_ui's name-local
        self.extra_names = extra_names
        self.exact: dict[str, set[str]] = {}       # literal -> {enclosing func names}
        self.prefixes: dict[str, set[str]] = {}
        self._func_stack: list[str] = []

    def _emit(self, literal: str, kind: str) -> None:
        # a bare "name" local carries the stripped prefix (shared_ui): re-attach it.
        full = literal
        if self.prefix and not literal.startswith("/"):
            full = self.prefix + literal
        # a URL route always starts with "/"; a bare-Name ``path`` local reused for a
        # non-route key (dials_surface's dial-key checks) is not a route — drop it.
        if not full.startswith("/"):
            return
        func = self._func_stack[-1] if self._func_stack else "<module>"
        tgt = self.exact if kind == "exact" else self.prefixes
        tgt.setdefault(full, set()).add(func)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        if _is_path_expr(node.left, self.extra_names):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)):
                    s = _str_const(comp)
                    if s is not None:
                        self._emit(s, "exact")
                elif isinstance(op, (ast.In, ast.NotIn)) and isinstance(comp, (ast.Tuple, ast.List)):
                    for el in comp.elts:
                        s = _str_const(el)
                        if s is not None:
                            self._emit(s, "exact")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        f = node.func
        if (isinstance(f, ast.Attribute) and f.attr == "startswith"
                and _is_path_expr(f.value, self.extra_names) and node.args):
            s = _str_const(node.args[0])
            if s is not None:
                self._emit(s, "prefix")
        self.generic_visit(node)


def scan_routes() -> list[dict]:
    """Every route literal across scanner.py + the delegated modules, merged and sorted."""
    exact: dict[str, dict] = {}
    prefixes: dict[str, dict] = {}

    def merge(store: dict[str, dict], found: dict[str, set[str]], source: str) -> None:
        for lit, funcs in found.items():
            row = store.setdefault(lit, {"sources": set(), "funcs": set()})
            row["sources"].add(source)
            row["funcs"].update(funcs)

    for mod, prefix, extra in [("scanner", "", set())] + [
        (m, "/shared/" if m == "shared_ui" else "", {"name"} if m == "shared_ui" else set())
        for m in _DELEGATED
    ]:
        src = _module_file(mod).read_text(encoding="utf-8")
        sc = _RouteScan(prefix, extra)
        sc.visit(ast.parse(src))
        merge(exact, sc.exact, f"{mod}.py")
        merge(prefixes, sc.prefixes, f"{mod}.py")

    routes = []
    for lit, row in exact.items():
        routes.append({"path": lit, "match": "exact",
                       "sources": sorted(row["sources"]), "funcs": sorted(row["funcs"])})
    for lit, row in prefixes.items():
        routes.append({"path": lit, "match": "prefix",
                       "sources": sorted(row["sources"]), "funcs": sorted(row["funcs"])})
    routes.sort(key=lambda r: (r["path"], r["match"]))
    return routes


# ── CONTROLS ────────────────────────────────────────────────────────────────
#
# The W7.3 census reads the STATIC DOM with html.parser; but three surfaces
# (dials, tutorial, and much of conceptric2 / review_surface) author their entire
# control layer inside <script> template literals, invisible to a static-DOM walk.
# A census whose job is "no un-verdicted chrome" cannot let a whole surface read as
# zero controls, so the control scan is a comment-stripped tag tokenizer over the
# RAW source — it sees a ``<button>`` whether it is in the served DOM or emitted from
# a JS template string. Control GROUPS (``data-cgroup``) stay on html.parser: they
# are static DOM (the W7.3 tests prove it) and need the folded/trigger structure.

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_TAG_RE = re.compile(r"<([a-zA-Z][-a-zA-Z0-9]*)\b([^>]*)>")
_ATTR_RE = re.compile(
    r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")
_TEXT_AFTER = re.compile(r"\s*([^<]*)")


def _attrs(blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _ATTR_RE.finditer(blob):
        key = m.group(1).lower()
        val = m.group(2) or m.group(3) or m.group(4) or ""
        out.setdefault(key, val)
    return out


def _control_row(surface: str, tag: str, a: dict, seq: int, text: str) -> dict | None:
    is_button = tag == "button" or a.get("role") == "button"
    is_link = tag == "a" and "href" in a
    is_select = tag == "select"
    has_onclick = "onclick" in a
    if not (is_button or is_link or is_select or has_onclick):
        return None
    kind = ("button" if is_button else "link" if is_link
            else "select" if is_select else "onclick")
    handle = (a.get("id") or a.get("data-view") or a.get("data-act")
              or a.get("name") or a.get("aria-label") or "")
    label = (handle or a.get("aria-label", "") or a.get("title", "")
             or text.strip() or a.get("href", "") or a.get("onclick", "") or kind)
    rec = {
        "surface": surface, "kind": kind, "tag": tag,
        "id_attr": a.get("id", ""), "handle": handle,
        "href": a.get("href", ""), "onclick": a.get("onclick", ""),
        "role": a.get("role", ""), "aria_label": a.get("aria-label", ""),
        "title": a.get("title", ""), "seq": seq,
        "label": " ".join(label.split())[:80],
    }
    stable = rec["id_attr"] or rec["handle"]
    key = f"#{stable}" if stable else f"{rec['kind']}@{seq}"
    rec["id"] = f"{surface}::{key}"
    return rec


class _GroupParser(HTMLParser):
    """The W7.3 static-DOM half: every ``data-cgroup`` element, its folded state, and
    the ``data-cg-fold`` disclosure triggers (unchanged idiom)."""

    def __init__(self, surface: str) -> None:
        super().__init__(convert_charrefs=True)
        self.surface = surface
        self.groups: list[dict] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        a = {k: (v if v is not None else "") for k, v in attrs}
        if "data-cgroup" in a:
            folded = ("data-cg-folded" in a) or ("hidden" in a) \
                or ("display:none" in a.get("style", "").replace(" ", ""))
            self.groups.append({
                "surface": self.surface, "name": a.get("data-cgroup") or tag,
                "gid": a.get("id", ""), "folded": bool(folded),
            })


def _scan_surface(surface: str, text: str) -> tuple[list[dict], list[dict]]:
    clean = _COMMENT_RE.sub("", text)
    controls: list[dict] = []
    seq = 0
    for m in _TAG_RE.finditer(clean):
        tag = m.group(1).lower()
        if tag not in ("button", "a", "select") and "onclick" not in m.group(2).lower() \
                and "role" not in m.group(2).lower():
            continue
        after = _TEXT_AFTER.match(clean, m.end())
        text_after = after.group(1) if after else ""
        seq += 1
        row = _control_row(surface, tag, _attrs(m.group(2)), seq, text_after)
        if row is not None:
            controls.append(row)
    gp = _GroupParser(surface)
    gp.feed(text)
    return controls, gp.groups


def scan_controls() -> tuple[list[dict], list[dict]]:
    controls: list[dict] = []
    groups: list[dict] = []
    for path in _html_surfaces():
        c, g = _scan_surface(path.name, path.read_text(encoding="utf-8"))
        controls.extend(c)
        groups.extend(g)
    controls.sort(key=lambda c: (c["surface"], c["seq"]))
    # disambiguate duplicate ids (repeated handles in template loops) deterministically.
    seen: dict[str, int] = {}
    for c in controls:
        n = seen.get(c["id"], 0)
        seen[c["id"]] = n + 1
        if n:
            c["id"] = f"{c['id']}~{n}"
    groups.sort(key=lambda g: (g["surface"], g["name"]))
    return controls, groups


# ── PANE-MODULE CONTROLS (the runtime-authored control layer) ────────────────
#
# THE C1 FINDING (AUDIT_2026-07-15 §C1, F8): the W5/W6/W7 rebuilt surfaces
# (desk.html, pipeline.html, assets.html) author ZERO control markup in their
# *.html — their ENTIRE interactive layer is rendered at runtime from
# ``static_shared/*-panes.mjs``. The html scan above (even over RAW source) never
# opens those .mjs files, so those three surfaces read as ZERO controls and the
# sealed "double-zero" was blind to them. This scanner reads the pane modules and
# folds their control sites into the census as ``kind='control'`` rows (surface =
# the CONSUMING .html), each carrying ``pane`` = the .mjs source so a reader tells
# pane-scanned from html-scanned at a glance.
#
# THE MAP is mechanical: every rebuilt *.html carries exactly one
# ``import { init… } from "/shared/X-panes.mjs"``, so the consuming surface is
# derived from that import (never hand-kept). The SCANNED SET is RESTRICTED to the
# four modules §C1 names — the three double-zero surfaces (desk/pipeline/assets)
# plus storyboard (its run/restructure/coverage panes). ``artefact-panes.mjs`` and
# ``conceptric-panes.mjs`` are a NAMED FOLLOW-ON: their surfaces already carry
# html-scanned control rows (they were never the double-zero blind case this F8
# closes), so their pane layer is left for a later scan rather than folded here.
_PANE_MODULES = ["desk-panes.mjs", "pipeline-panes.mjs",
                 "assets-panes.mjs", "storyboard-panes.mjs"]

_STATIC = _SRC / "web" / "static_shared"

# framework/style class tokens that never make a good stable slug (shared chrome
# classes, arm-to-fire state markers) — skipped when a distinctive class is sought.
_GENERIC_CLASS = {"armed", "compose", "destructive", "busy", "dk-act", "dk-zone",
                  "dk-zone-full", "no-fold", "no-drag", "zone-context",
                  "zone-consequences", "zone-tools", "zone-deeplinks", "primary"}


def _pane_surface_map() -> dict[str, str]:
    """Each scanned pane module → the .html surface that imports it, derived
    mechanically from the ``/shared/<module>`` import literal in the served HTML."""
    out: dict[str, str] = {}
    htmls = list((_SRC / "web").glob("*.html"))
    for mod in _PANE_MODULES:
        needle = f"/shared/{mod}"
        for html in sorted(htmls):
            if needle in html.read_text(encoding="utf-8"):
                out[mod] = html.name
                break
    return out


def _strip_js_comments(src: str) -> str:
    """Remove ``//`` line comments and ``/* */`` block comments that sit OUTSIDE a
    string/template literal, so a ``<button>`` written in a code comment never reads
    as a control. String contents (where the control markup actually lives, in
    ``"…"``/``'…'`` concatenations) are preserved verbatim; backtick templates are
    kept opaque (the modules author no control tags inside them)."""
    out: list[str] = []
    i, n = 0, len(src)
    quote: str | None = None
    while i < n:
        c = src[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1]); i += 2; continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"', "`"):
            quote = c; out.append(c); i += 1; continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            i += 2
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c); i += 1
    return "".join(out)


_FUNC_RE = re.compile(
    r"(?:(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_$]+)"
    r"|(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*"
    r"(?:async\s+)?(?:\([^)]*\)|[A-Za-z0-9_$]+)\s*=>)")   # arrow fns only — not a bare `const x = (expr)`


def _enclosing_funcs(text: str) -> list[tuple[int, str]]:
    """(position, name) of every function definition, for naming a control by its
    enclosing function when it carries no stable attribute/label of its own."""
    out: list[tuple[int, str]] = []
    for m in _FUNC_RE.finditer(text):
        out.append((m.start(), m.group(1) or m.group(2) or ""))
    return out


def _literal_head(val: str) -> str:
    """The stable LITERAL HEAD of an attribute value — the fragment before the first
    JS boundary (``"`` ``'`` ``+`` ``{`` `` ` `` ``<``). An attribute broken by
    concatenation (``'sb-retire" + (armed ? …)``, ``'hy-chip " + (n ? …) + " sb-cov'``)
    keeps only its stable head, so a JS variable in a ternary never leaks into a slug."""
    stop = len(val)
    for ch in ('"', "'", "+", "{", "`", "<"):
        p = val.find(ch)
        if p != -1:
            stop = min(stop, p)
    return val[:stop]


def _slugify(raw: str, limit: int = 4) -> str:
    """A stable slug from a literal run: lowercase word tokens (letters/digits),
    the first ``limit`` joined by ``-``."""
    toks = re.findall(r"[A-Za-z0-9]+", _literal_head(raw))
    return "-".join(t.lower() for t in toks[:limit])


def _distinctive_class(cls_val: str) -> str:
    """The first class token that is neither a framework/state generic nor an
    ``hy-``/``is-`` prefixed shared-chrome class — the stable, meaningful one. Read
    from the class value's LITERAL HEAD only (never a JS ternary spliced into it)."""
    for tok in re.findall(r"[A-Za-z0-9_-]+", _literal_head(cls_val)):
        low = tok.lower()
        if low in _GENERIC_CLASS or low.startswith(("hy-", "is-")):
            continue
        return low
    return ""


def _pane_text_after(clean: str, end: int) -> str:
    """The LITERAL text immediately after a tag's ``>`` — up to the first JS/markup
    boundary (``<`` ``"`` ``'`` ``+`` ``{`` `` ` ``). Empty when the text is a JS
    expression (``esc(d.label)…``), so only a real static label ever slugs."""
    seg = clean[end:end + 120]
    stop = len(seg)
    for ch in ("<", '"', "'", "+", "{", "`"):
        p = seg.find(ch)
        if p != -1:
            stop = min(stop, p)
    return seg[:stop].strip()


def _pane_control(surface: str, mod: str, tag: str, attrs: dict, text: str,
                  funcname: str) -> dict | None:
    """One pane control row, or None when the tag is not an interactive control.
    Parallel to the html-scanned control set: ``<button>`` / ``[role=button]`` /
    ``<a href>`` / ``<select>`` / ``[onclick]``."""
    is_button = tag == "button" or attrs.get("role") == "button"
    is_link = tag == "a" and "href" in attrs
    is_select = tag == "select"
    has_onclick = "onclick" in attrs
    if not (is_button or is_link or is_select or has_onclick):
        return None
    ctrl_kind = ("button" if is_button else "link" if is_link
                 else "select" if is_select else "onclick")
    # slug: a static id → distinctive class → literal label text → data-* name →
    # the enclosing function. Deterministic and never a raw line number.
    id_slug = _slugify(attrs.get("id", ""))
    cls_slug = _distinctive_class(attrs.get("class", ""))
    txt_slug = _slugify(text)
    data_slug = next((k[5:] for k in attrs if k.startswith("data-")), "")
    slug = (id_slug or cls_slug or txt_slug or _slugify(data_slug)
            or _slugify(funcname) or ctrl_kind)
    stem = mod[:-4] if mod.endswith(".mjs") else mod        # "desk-panes"
    label = (attrs.get("id") or (text if text else "")
             or _distinctive_class(attrs.get("class", "")) or funcname or ctrl_kind)
    return {
        "surface": surface,
        "id": f"{surface}::{stem}:{ctrl_kind}:{slug}",
        "ctrl_kind": ctrl_kind,
        "pane": mod,
        "label": " ".join(str(label).split())[:80],
    }


def _scan_pane_module(surface: str, mod: str, text: str) -> list[dict]:
    clean = _strip_js_comments(text)
    funcs = _enclosing_funcs(clean)
    rows: list[dict] = []
    for m in _TAG_RE.finditer(clean):
        tag = m.group(1).lower()
        blob = m.group(2)
        low = blob.lower()
        if tag not in ("button", "a", "select") and "onclick" not in low \
                and "role" not in low:
            continue
        # nearest enclosing function name at this position (stable, not a line no.).
        fname = ""
        for pos, name in funcs:
            if pos <= m.start():
                fname = name
            else:
                break
        row = _pane_control(surface, mod, tag, _attrs(blob),
                            _pane_text_after(clean, m.end()), fname)
        if row is not None:
            rows.append(row)
    return rows


# ── THE DESK COCKPIT VERB-TOOLS (roster-derived) ─────────────────────────────
#
# The desk cockpit renders ONE arm-to-fire tool per (class, verb) in the read-model
# it is handed — ``desk-panes.mjs`` verbButton() builds each from ``row.verbs``, and
# that verb VOCABULARY is authored in ``desk.py`` (``_DESK_CLASSES``), NOT in the
# .mjs. A single idiom-scanned verbButton() site could not honestly carry a verdict
# (the SAME site renders both live doors and the fail-closed lifts), so the desk
# verb-tools are enumerated per (class, verb) from that authoritative roster. Each
# is an individually-adjudicable control: a COMPOSE verb renders as a nav link (it
# opens the working surface to compose); every other verb renders as a button
# POSTing /desk/act — WIRED when its executor exists, else the fail-closed 422 the
# ``_DEFERRED_VERBS`` ruling names (the kept-unwired lifts, by design).

def _py_literal(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def _desk_roster() -> tuple[list[tuple[str, str]], set[str]]:
    """((class, verb) pairs in authored order, COMPOSE verb set) — the (class,verb)
    pairs from ``desk.py:_DESK_CLASSES`` and the COMPOSE set from
    ``desk-panes.mjs``. Deferred (fail-closed) pairs come from ``_desk_deferred``."""
    tree = ast.parse((_SRC / "web" / "desk.py").read_text(encoding="utf-8"))
    pairs: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        target = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and target.id == "_DESK_CLASSES" and value is not None:
            for el in getattr(value, "elts", []):
                d = _py_literal(el) or {}
                cls = d.get("class")
                for verb in d.get("verbs") or []:
                    if cls:
                        pairs.append((cls, verb))
    compose = set()
    mtxt = (_STATIC / "desk-panes.mjs").read_text(encoding="utf-8")
    mm = re.search(r"COMPOSE\s*=\s*new\s+Set\(\[([^\]]*)\]\)", mtxt)
    if mm:
        compose = {t.strip() for t in re.findall(r"[\"']([^\"']+)[\"']", mm.group(1))}
    return pairs, compose


def _desk_deferred() -> set[tuple[str, str]]:
    """The (class, verb) pairs the desk door fails closed on (``desk.py:_DEFERRED_VERBS``)."""
    tree = ast.parse((_SRC / "web" / "desk.py").read_text(encoding="utf-8"))
    out: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        target = value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and target.id == "_DEFERRED_VERBS" and value is not None:
            for key in getattr(value, "keys", []):
                pair = _py_literal(key)
                if isinstance(pair, tuple) and len(pair) == 2:
                    out.add((pair[0], pair[1]))
    return out


def _desk_verb_controls() -> list[dict]:
    pairs, compose = _desk_roster()
    deferred = _desk_deferred()
    rows: list[dict] = []
    for cls, verb in pairs:
        is_compose = verb in compose                    # rendered as a nav link
        ctrl_kind = "link" if is_compose else "button"
        rows.append({
            "surface": "desk.html",
            "id": f"desk.html::desk-panes:verb:{cls}.{verb}",
            "ctrl_kind": ctrl_kind,
            "pane": "desk-panes.mjs",
            "label": f"{cls} · {verb}",
            # carried so the verdict generator can adjudicate deterministically.
            "desk_verb": {"class": cls, "verb": verb,
                          "compose": is_compose, "deferred": (cls, verb) in deferred},
        })
    return rows


# ── THE PIPELINE SUB-ORGAN FIRE CONTROLS (roster-derived) ────────────────────
#
# THE CONJUGATE WAVE (SCOUT_2026-07-17): each night-organ card on /pipeline carries
# at most ONE scoped fire control — a launch button ``run-tray.mjs`` builds via
# ``document.createElement`` (never a literal ``<button>`` tag) FROM the sub-organ's
# ``fire_action``. A tag-scan of ``pipeline-panes.mjs`` is blind to it (the button is
# programmatic and lives in ``run-tray.mjs``, a module ``_scan_pane_module`` never
# opens), exactly as the desk cockpit's verb-tools were blind to the html scan — so
# the fire controls ride their AUTHORITATIVE ROSTER the same way
# ``_desk_verb_controls`` rides ``_DESK_CLASSES``: ``pipeline_surface.
# _SUBORGAN_FOR_STATE`` names each sub-organ's ``fire_action`` and
# ``storyboard._LOCAL_SAFE`` / ``_MODEL_HEAVY`` name its cost class (local-safe fires
# the executor; model-heavy banks a work-order). BOTH fire through the ONE door
# ``POST /storyboard/run/launch``, so every rostered fire is WIRED — never a dead
# button (the dead-button-drift catch, SCOUT RISK 5).
#
# SCOPED to the sub-organ band THIS wave adds: the pre-existing organ-card launch
# controls (``_ACTION_ORGAN`` — storyboard-rebuild / harnessed-round / dream …, the
# same run-tray roster the storyboard run pane also mounts) predate this wave on both
# surfaces and stay a NAMED FOLLOW-ON — the same boundary ``_PANE_MODULES`` draws
# around artefact-/conceptric-panes.mjs.

def _suborgan_fires() -> list[tuple[str, str]]:
    """((sub-organ id, fire_action) pairs, authored order) from
    ``pipeline_surface._SUBORGAN_FOR_STATE`` — the sub-organs whose card renders a
    scoped fire control (a non-None ``fire_action``). Read from the source AST, never
    a hand-kept list, so a new sub-organ fire is enumerated the moment it joins."""
    tree = ast.parse((_SRC / "web" / "pipeline_surface.py").read_text(encoding="utf-8"))
    table = None
    for node in ast.walk(tree):
        target = value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if (isinstance(target, ast.Name) and target.id == "_SUBORGAN_FOR_STATE"
                and value is not None):
            table = _py_literal(value)
            break
    pairs: list[tuple[str, str]] = []
    for subs in (table or {}).values():
        for sub in subs or []:
            action = (sub or {}).get("fire_action")
            if action:
                pairs.append((sub.get("id"), action))
    return pairs


def _launch_cost() -> dict[str, str]:
    """action → cost class ('local-safe' | 'model-heavy') from storyboard's launch
    rosters (``_LOCAL_SAFE`` tuple / ``_MODEL_HEAVY`` dict) — the mechanism that
    decides whether a fire runs the executor (``run_launch``) or banks a work-order
    (``bank_work_order``)."""
    tree = ast.parse((_SRC / "manuscript" / "storyboard.py").read_text(encoding="utf-8"))
    local: tuple = ()
    heavy: dict = {}
    for node in ast.walk(tree):
        target = value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and value is not None:
            if target.id == "_LOCAL_SAFE":
                local = _py_literal(value) or ()
            elif target.id == "_MODEL_HEAVY":
                heavy = _py_literal(value) or {}
    out = {a: "local-safe" for a in local}
    out.update({a: "model-heavy" for a in heavy})
    return out


def _pipeline_suborgan_controls() -> list[dict]:
    """Every sub-organ scoped fire on /pipeline, one control row per (sub-organ,
    fire_action), folded to ``pipeline.html`` (the consuming surface). The cost class
    is carried so the verdict generator adjudicates the mechanism deterministically
    (local-safe → ``run_launch``; model-heavy → ``bank_work_order``)."""
    cost = _launch_cost()
    rows: list[dict] = []
    for sub_id, action in _suborgan_fires():
        rows.append({
            "surface": "pipeline.html",
            "id": f"pipeline.html::pipeline-panes:fire:{sub_id}.{action}",
            "ctrl_kind": "button",
            "pane": "pipeline-panes.mjs",
            "label": f"{sub_id} · {action}",
            "suborgan_fire": {"suborgan": sub_id, "action": action,
                              "cost_class": cost.get(action, "")},
        })
    return rows


def scan_pane_controls() -> list[dict]:
    """Every pane-authored control across the four scanned modules, folded to its
    consuming surface. Deterministic: modules in a fixed order, source order within
    a module, duplicate ids disambiguated with a stable ``~n`` suffix (the html-scan
    idiom). The desk cockpit's verb-tools ride the roster (see _desk_verb_controls)."""
    surf_map = _pane_surface_map()
    rows: list[dict] = []
    for mod in _PANE_MODULES:
        surface = surf_map.get(mod)
        if not surface:
            continue
        text = (_STATIC / mod).read_text(encoding="utf-8")
        rows.extend(_scan_pane_module(surface, mod, text))
    # the desk verb-tools (roster-derived) are the desk cockpit's action controls.
    rows.extend(_desk_verb_controls())
    # the conjugate-wave sub-organ fires (roster-derived) — the /pipeline night-organ
    # scoped launch buttons run-tray.mjs builds programmatically (the tag scan is blind).
    rows.extend(_pipeline_suborgan_controls())
    seen: dict[str, int] = {}
    for r in rows:
        k = seen.get(r["id"], 0)
        seen[r["id"]] = k + 1
        if k:
            r["id"] = f"{r['id']}~{k}"
    rows.sort(key=lambda r: (r["surface"], r["id"]))
    return rows


# ── ASSEMBLY ────────────────────────────────────────────────────────────────

def census() -> dict:
    routes = scan_routes()
    controls, groups = scan_controls()
    controls = controls + scan_pane_controls()            # fold the runtime pane layer in
    by_surface: dict[str, int] = {}
    for c in controls:
        by_surface[c["surface"]] = by_surface.get(c["surface"], 0) + 1
    counts = {
        "routes": len(routes),
        "routes_exact": sum(1 for r in routes if r["match"] == "exact"),
        "routes_prefix": sum(1 for r in routes if r["match"] == "prefix"),
        "controls": len(controls),
        "groups": len(groups),
        "surfaces": len(_html_surfaces()),
        "controls_by_surface": dict(sorted(by_surface.items())),
    }
    return {"routes": routes, "controls": controls, "groups": groups, "counts": counts}


def main() -> int:
    json.dump(census(), sys.stdout, indent=2, sort_keys=False, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
