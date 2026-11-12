"""The PROJECTION VIEWER - see the projected artefact and the provenance of its statements.

The author's requirement (2026-07-02): "One should be able to _see_ the projected
artefact, and the provenance of its statements in the viewer... live edit both the
tex and the compiled document, and have this origin tracing of statements, at least
broadly." Granularity: paragraph/section spans, not words.

Three panes served from one page (``projection_viewer.html``): the tex (editable),
the compiled PDF, and the provenance rail - the spans the projector emitted as
structured comments (``% PLAN:S1`` / ``% NODES: res:window-verdict, ...``), each
resolvable back to its source nodes through the SAME corpus network the navigator
uses (``corpus_ingest.corpus_network`` - reused, never reimplemented, and never
embedding: views never embed).

Pure handler module: the scanner owns the HTTP server and dispatches ``/projection*``
here via :func:`handle`. This module never starts a server, never edits the scanner,
and never spawns anything but the LaTeX toolchain (latexmk first, pdflatex twice as
the fallback - both bounded by a hard timeout so a wedged compile can never hang the
scanner's request thread).

File access is fenced to the repo root: every ``file=`` param resolves and must land
inside the repo, so ``..`` traversal and absolute escapes are rejected with a 403.

Raw edits use the existing ``GET /projection/tex?view=source`` observation: the
canonical file, displayed content and ``expected_source_digest`` come from one
physical read. Save and restore compare that original digest under the shared
source lease before replacing bytes or banking a version. Ordinary GET remains
plain text. A stale/missing guard returns 409 and an explicit inspection route;
the editor must keep its draft rather than obtain a fresh token at Save.
"""

from __future__ import annotations
from laplace.core import observe

import hashlib
import html as _html
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlencode
from pathlib import Path
from typing import Any

_HTML = Path(__file__).resolve().parent / "projection_viewer.html"

# LaTeX toolchain bounds - generous for a real paper, hard so the server never hangs.
_LATEXMK_TIMEOUT = 240
_PDFLATEX_TIMEOUT = 120

# provenance markers the projector emits into the tex
_PLAN_RE = re.compile(r"^\s*%+\s*PLAN\s*:\s*(\S+)")
_NODES_RE = re.compile(r"^\s*%+\s*NODES\s*:\s*(.+?)\s*$")
# per-paragraph marker (% <sid>-pN) — the finer join key; mirrors
# schema.PARA_MARKER_RE (the viewer keeps its own marker dialect, like the two
# above). Whole comment body is one token ending -p<digits>, so it can never
# collide with PLAN:/NODES:.
_PARA_RE = re.compile(r"^\s*%+\s*(\S+-p\d+)\s*$")
# a NODES marker may carry a parenthesised aside next to (or instead of) its ids —
# `res:integer-decoder (evidence)`, `% NODES: (step back: what the object achieved)`.
# No conceptric id contains a parenthesis, so the aside is dropped before the split
# and its words never reach the id sets.
_NODES_ASIDE_RE = re.compile(r"\([^()]*\)")

# document structure - \input{S1} / \include{S1} lines in a root tex (comments excluded)
_INPUT_RE = re.compile(r"^\s*\\(?:input|include)\{([^}]+)\}")
_DOCCLASS_RE = re.compile(r"^\s*\\documentclass", re.M)

_JSON = "application/json; charset=utf-8"


def _repo_root() -> Path:
    from laplace.core.checkout import repo_root as rr   # the serving checkout's owner (the server module held the same object under an old name)
    return rr()


# ---------------------------------------------------------------------------
# path fence - every file= param resolves INSIDE the repo or is refused
# ---------------------------------------------------------------------------

def _safe_path(file_param: str, repo_root: Path | None = None) -> Path | None:
    """Resolve ``file_param`` (repo-relative or absolute) to a path inside the repo.

    Returns None for anything that escapes the repo root - ``..`` traversal,
    absolute paths elsewhere, drive changes. The fence is the resolved-containment
    check, so symlink/`..` tricks collapse before the comparison."""
    if not file_param:
        return None
    # A Windows drive path is absolute-elsewhere by intent even when this process runs
    # on POSIX (where "C:/..." parses as relative and would nest inside the repo).
    if re.match(r"^[A-Za-z]:[/\\]", file_param):
        return None
    root = (repo_root or _repo_root()).resolve()
    p = Path(file_param)
    if not p.is_absolute():
        p = root / p
    try:
        p = p.resolve()
    except OSError:
        return None
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p


# ---------------------------------------------------------------------------
# provenance map - % PLAN:S1 / % NODES: ... comments -> spans
# ---------------------------------------------------------------------------

def parse_map(text: str) -> list[dict[str, Any]]:
    """Parse the projector's structured comments into provenance spans.

    Each ``% PLAN:<sec>`` / ``% NODES: a, b`` marker opens a span running to the
    next marker or EOF. Markers separated only by blank/marker lines merge into ONE
    span (the projector emits PLAN immediately followed by NODES for the same block),
    and the most recent PLAN section carries forward into later NODES-only spans.
    Lines are 1-based inclusive. Returns [{start_line, end_line, section, nodes}]."""
    lines = text.splitlines()
    markers: list[tuple[int, str, Any]] = []          # (0-based line, kind, value)
    for i, ln in enumerate(lines):
        m = _PLAN_RE.match(ln)
        if m:
            markers.append((i, "plan", m.group(1)))
            continue
        m = _NODES_RE.match(ln)
        if m:
            # commas are the convention; blind builders sometimes emit spaces -
            # accept both (ids never contain either)
            body = _NODES_ASIDE_RE.sub(" ", m.group(1))
            nodes = [t for chunk in body.split(",")
                     for t in chunk.split() if t]
            markers.append((i, "nodes", nodes))
    if not markers:
        return []

    # group adjacent markers (only blank lines between) into one span head
    groups: list[list[tuple[int, str, Any]]] = [[markers[0]]]
    for prev, cur in zip(markers, markers[1:]):
        between = lines[prev[0] + 1:cur[0]]
        if all(not b.strip() for b in between):
            groups[-1].append(cur)
        else:
            groups.append([cur])

    spans: list[dict[str, Any]] = []
    section = ""
    for gi, grp in enumerate(groups):
        start = grp[0][0]
        end = groups[gi + 1][0][0] - 1 if gi + 1 < len(groups) else len(lines) - 1
        nodes: list[str] = []
        for _, kind, val in grp:
            if kind == "plan":
                section = val
            else:
                nodes.extend(val)
        spans.append({"start_line": start + 1, "end_line": end + 1,
                      "section": section, "nodes": nodes})
    return spans


def load_map(tex_path: Path) -> list[dict[str, Any]]:
    """The provenance spans for a tex file: parsed markers, with a sidecar
    ``<texname>.provenance.json`` (projector-emitted, ground truth when present)
    preferred over the comment parse."""
    parsed = parse_map(tex_path.read_text(encoding="utf-8", errors="replace"))
    for sidecar in (tex_path.with_suffix(".provenance.json"),
                    tex_path.with_name(tex_path.name + ".provenance.json")):
        if sidecar.is_file():
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                data = data.get("spans", [])
            if isinstance(data, list) and data:
                return data                       # the projector's own ledger wins
    return parsed


def parse_paragraphs(text: str) -> list[dict[str, Any]]:
    """Finer-than-section provenance: each ``% <sid>-pN`` marker (the realiser and
    the weld emit one before every rendered paragraph) opens a span carrying its
    ``spec_id`` (== the narrative/prose-provenance ``paragraph_id``) and its section.

    The mapping is many-to-many (his model, this session): the weld may MERGE plan
    paragraphs — their markers sit adjacently (only blank lines between) at the top
    of one paragraph, which then carries MULTIPLE ``spec_ids`` — or SPLIT one, its
    ``spec_id`` repeating across the parts. Adjacent markers group into one span;
    prose between markers starts a new one.

    Complements :func:`parse_map`, which STAYS section-granular — the dirty diff
    and the six ledger/anchor consumers depend on that shape. Lines are 1-based
    inclusive. Returns [{start_line, end_line, spec_ids, spec_id, section}]
    (``spec_id`` = ``spec_ids[0]``, kept for single-value callers); empty when the
    fragment carries no paragraph markers (older or non-staged tex)."""
    lines = text.splitlines()
    section = ""
    marks: list[tuple[int, str, str]] = []        # (0-based line, spec_id, section)
    plan_lines: list[int] = []
    for i, ln in enumerate(lines):
        mp = _PLAN_RE.match(ln)
        if mp:
            section = mp.group(1)
            plan_lines.append(i)
            continue
        m = _PARA_RE.match(ln)
        if m:
            marks.append((i, m.group(1), section))
    if not marks:
        return []
    boundaries = sorted(plan_lines + [i for i, _, _ in marks])
    # group markers separated only by blank/marker lines (no prose, no PLAN) — a
    # MERGED paragraph — into one span carrying every joined spec_id.
    groups: list[list[tuple[int, str, str]]] = [[marks[0]]]
    for prev, cur in zip(marks, marks[1:]):
        between = lines[prev[0] + 1:cur[0]]
        if all((not b.strip()) or _PARA_RE.match(b) for b in between):
            groups[-1].append(cur)
        else:
            groups.append([cur])
    spans: list[dict[str, Any]] = []
    for grp in groups:
        last = grp[-1][0]
        nxt = next((b for b in boundaries if b > last), len(lines))
        spec_ids = [s for _, s, _ in grp]
        spans.append({"start_line": grp[0][0] + 1, "end_line": nxt,
                      "spec_ids": spec_ids, "spec_id": spec_ids[0],
                      "section": grp[0][2]})
    return spans


def load_paragraphs(tex_path: Path) -> list[dict[str, Any]]:
    """Paragraph spans for a tex file (the finer companion to :func:`load_map`)."""
    return parse_paragraphs(tex_path.read_text(encoding="utf-8", errors="replace"))


# ---------------------------------------------------------------------------
# document model - the multi-file paper (root + \input fragments, in order)
# ---------------------------------------------------------------------------

def _input_names(text: str) -> list[str]:
    """The \\input/\\include arguments of a tex source, in document order."""
    return [m.group(1).strip() for ln in text.splitlines()
            if (m := _INPUT_RE.match(ln))]


def _frag_path(root_dir: Path, name: str) -> Path:
    """Resolve one \\input argument the way TeX does: relative to the root's
    directory, ``.tex`` appended when the argument carries no suffix."""
    p = root_dir / name
    return p if p.suffix else p.with_suffix(".tex")


class CompileRootRefused(ValueError):
    def __init__(self, message: str, reason: str = 'compile-root-unproved', *, corpus: str = ''):
        super().__init__(message); self.reason = reason; self.corpus = corpus

    def response(self) -> dict:
        from laplace.manuscript.build_targets import error_details
        derived = error_details(self)
        if derived:
            return {'error':str(self),'reason':self.reason,'status':409,**derived}
        out = {'error':str(self), 'reason':self.reason, 'status':409,
               'recovery':'Inspect the project source/candidates and use its existing explicit source selection; reopen this file. No root was guessed.'}
        if self.corpus:
            out['next_read'] = {'http':{'method':'GET','url':'/authoring/context?'+urlencode({'project':self.corpus})}}
            out['source_selection'] = {'http':{'method':'POST','url':'/authoring/edition'},
                                       'project':self.corpus,'requires':['explicit root from current candidates','base_revision']}
        return out


def _compile_scope(p: Path, *, corpus: str = '', compile_root: str = '',
                   repo_root: Path | None = None, _selection: dict | None = None,
                   build_target: dict | None = None) -> dict:
    """One addressed selection and exact include membership per request.

    Project selection is authoritative; an expected root cannot silently adopt
    a changed selection. Standalone documentclass input may address itself, but
    an unqualified fragment needs an explicit root. Never searches neighbours.
    """
    from laplace.manuscript import manuscript_source
    rr = (repo_root or _repo_root()).resolve(); p = p.resolve()
    if not p.is_relative_to(rr):raise CompileRootRefused('source file escapes the active checkout')
    if build_target is not None:
        from laplace.manuscript import build_targets
        try:
            root = build_targets.resolve(build_target,corpus,rr)
        except build_targets.TargetRefused as error:
            raise CompileRootRefused(str(error),'derived-build-target-changed',corpus=corpus) from error
        if compile_root and _safe_path(compile_root,rr)!=root:
            raise CompileRootRefused('The requested compile root differs from the issued derived target.',corpus=corpus)
        if build_target.get('kind')=='candidate':
            if p not in {root,root.with_suffix('.pdf')}:
                raise CompileRootRefused('A candidate build addresses only its exact issued private root.',corpus=corpus)
            return {'root':root,'source':None,'corpus':corpus,'build_target':build_target,
                'compile_root':root.relative_to(rr).as_posix(),'requested':p,
                'tree':{'files':[root.relative_to(rr).as_posix()],'diagnostics':[]}}
        tree = manuscript_source.traversal(root,repo_root=rr)
        member = p.with_suffix('.tex') if p.suffix.lower()=='.pdf' else p
        if tree.get('diagnostics') or member.relative_to(rr).as_posix() not in tree.get('files',[]):
            raise CompileRootRefused('The source is not in the complete issued derived include tree.',corpus=corpus)
        return {'root':root,'tree':tree,'source':None,'corpus':corpus,'build_target':build_target,
                'compile_root':root.relative_to(rr).as_posix(),'requested':p}
    selected = None
    if corpus:
        selected = _selection if _selection is not None else manuscript_source.resolve(corpus, repo_root=rr, include_candidates=False)
        if selected.get('project') != corpus:
            raise CompileRootRefused('The observed source selection belongs to another project.', corpus=corpus)
        if selected.get('status') != 'resolved' or not selected.get('root'):
            raise CompileRootRefused('The project has no unambiguous declared manuscript root; inspect its source selection.', corpus=corpus)
        root = (rr / selected['root']).resolve()
        if compile_root and _safe_path(compile_root, rr) != root:
            raise CompileRootRefused('The selected manuscript root changed since this reader was opened.', 'compile-root-selection-changed', corpus=corpus)
    else:
        root = _safe_path(compile_root, rr) if compile_root else p
        if root is None or not root.is_file() or not _DOCCLASS_RE.search(manuscript_source._uncomment(root.read_text(encoding='utf-8',errors='replace'))):
            raise CompileRootRefused('A fragment requires its explicit compile root or project source selection.')
    tree = manuscript_source.traversal(root, repo_root=rr)
    member = p.with_suffix('.tex') if p.suffix.lower() == '.pdf' else p
    if tree.get('diagnostics') or member.relative_to(rr).as_posix() not in tree.get('files', []):
        raise CompileRootRefused('The requested source is not a proved member of this complete selected include tree.', 'compile-root-membership-unproved', corpus=corpus)
    return {'root':root, 'tree':tree, 'source':selected, 'corpus':corpus,
            'compile_root':root.relative_to(rr).as_posix(), 'requested':p}


def resolve_root(p: Path, *, corpus: str = '', compile_root: str = '',
                 repo_root: Path | None = None) -> Path:
    return _compile_scope(p, corpus=corpus, compile_root=compile_root, repo_root=repo_root)['root']


def doc_model(file_param: str, *, corpus: str = '', compile_root: str = '') -> dict[str, Any]:
    """The document model the multi-file editor renders: the compile root plus
    every ``\\input`` fragment, in document order, each as a repo-relative path.

    Given a fragment, resolves up to its root first, so the viewer opened on
    S3.tex still sees the whole paper. Shape:
    ``{root, files: [{file, name, exists}]}`` - ``root`` repo-relative posix,
    ``files[0]`` the root itself."""
    p = _safe_path(file_param)
    if p is None:
        return {"error": "file must resolve inside the repo root"}
    if not p.is_file():
        return {"error": f"no such tex file: {file_param}"}
    scope = _compile_scope(p, corpus=corpus, compile_root=compile_root)
    root = scope['root']
    rr = _repo_root().resolve()

    def rel(q: Path) -> str:
        try:
            return q.relative_to(rr).as_posix()
        except ValueError:
            return str(q)

    from laplace.manuscript import manuscript_source
    expanded = scope['tree']
    files = [{"file": item["file"], "name": Path(item["file"]).stem,
              "exists": True, "order": item["order"],
              "parent": item["parent"], "include_line": item["include_line"]}
             for item in expanded["sources"]]
    return {"root": rel(root), "files": files,
            "includes": expanded["includes"], "diagnostics": expanded["diagnostics"]}


def source_model(project: str, edition: str | None = None) -> dict[str, Any]:
    """The registered source edition and its recursive file order for a projection.

    This is a source-model helper only; scanner routing remains the caller's job.
    """
    from laplace.manuscript import manuscript_source
    selected = manuscript_source.resolve(project, repo_root=_repo_root(), edition=edition)
    if selected.get("status") != "resolved" or not selected.get("root"):
        return {"source": selected, "traversal": None}
    return {"source": selected,
            "traversal": manuscript_source.traversal(selected["root"], repo_root=_repo_root())}


# ---------------------------------------------------------------------------
# corpus network - REUSED from corpus_ingest, cached, never embeds
# ---------------------------------------------------------------------------

_NET_CACHE: dict[str, tuple[float, dict]] = {}
_NET_LOCK = threading.Lock()


def _friction_mtime(name: str) -> float:
    f = _repo_root() / "corpus_friction" / f"{re.sub(r'[^a-z0-9_-]', '_', name)}.jsonl"
    try:
        return f.stat().st_mtime
    except OSError:
        return 0.0


def _network(corpus: str) -> dict | None:
    """The corpus conceptric via the one mechanism (corpus_ingest.corpus_network),
    cached at module level and invalidated when the friction ledger moves - so a
    rewiring lands in the viewer on the next fetch. NO embedding (views never embed:
    corpus_network builds semantic=False)."""
    from laplace.research import corpus_ingest as ci
    rr = _repo_root()
    troot = ci.resolve_corpus(rr, corpus)
    if not troot:
        return None
    mt = _friction_mtime(corpus)
    with _NET_LOCK:
        hit = _NET_CACHE.get(corpus)
        if hit and hit[0] == mt:
            return hit[1]
        net = ci.corpus_network(troot, repo_root=rr, name=corpus)
        _NET_CACHE[corpus] = (mt, net)
        return net


def residue(file_param: str, corpus: str) -> dict[str, Any]:
    """The COMPLEMENT of the projection (his ask, 2026-07-03): every live corpus
    node that no ``% NODES`` marker anywhere in the paper cites. The set
    difference is computed over the SAME two mechanisms the viewer already
    trusts - the doc model's file walk and the corpus network - so the residue
    is exactly what the provenance rail cannot reach. Retired nodes and the
    structural anchors (``paper://`` root, the references root) are excluded:
    they are not un-projected content, they are scaffolding."""
    model = doc_model(file_param, corpus=corpus)
    if "error" in model:
        return model
    net = _network(corpus)
    if net is None:
        return {"error": f"unknown corpus {corpus!r}"}
    mentioned: set[str] = set()
    for f in model["files"]:
        p = _safe_path(f["file"])
        if p is not None and p.is_file():
            for span in load_map(p):
                mentioned.update(span.get("nodes") or [])

    def is_scaffold(nid: str, nd: dict) -> bool:
        return nid.startswith("paper://") or nid == "references" \
            or nd.get("kind") in ("root", "references")

    by_kind: dict[str, list[dict[str, Any]]] = {}
    n_live = 0
    n_cites = 0
    for nid, nd in net.get("nodes", {}).items():
        proj = nd.get("projection") or {}
        if nd.get("retired") or proj.get("retired") or is_scaffold(nid, nd):
            continue
        if nd.get("kind") == "citation":
            # refs surface through \cite, not NODES markers - the armed citations
            # gate (check_corpus_citations) is their coverage proof, not this view
            n_cites += 1
            continue
        n_live += 1
        if nid in mentioned:
            continue
        by_kind.setdefault(nd.get("kind") or "?", []).append(
            {"id": nid, "essence": (nd.get("essence") or "")[:200],
             "grade": nd.get("grade")})
    for rows in by_kind.values():
        rows.sort(key=lambda r: r["id"])
    n_res = sum(len(v) for v in by_kind.values())
    return {"corpus": corpus, "root": model["root"], "n_live": n_live,
            "n_mentioned": len(mentioned), "n_residue": n_res,
            "n_citations_excluded": n_cites,
            "citations_note": "refs ride the \\cite citations gate, not NODES markers",
            "by_kind": dict(sorted(by_kind.items(),
                                   key=lambda kv: -len(kv[1])))}


def node_brief(corpus: str, nid: str) -> dict[str, Any]:
    """The origin-tracing payload for one node: essence + kind + the projection
    block (emit-time labels), plus the flags the rail renders."""
    net = _network(corpus)
    if net is None:
        return {"error": f"unknown corpus {corpus!r}"}
    node = net.get("nodes", {}).get(nid)
    if node is None:
        return {"error": f"unknown node {nid!r}", "id": nid, "corpus": corpus}
    return {"id": nid, "corpus": corpus,
            "kind": node.get("kind"),
            "essence": node.get("essence", ""),
            "projection": node.get("projection", {}),
            "grade": node.get("grade"),
            "parent": node.get("parent"),
            "retired": bool(node.get("retired")),
            "sealed": bool(node.get("sealed"))}


# ---------------------------------------------------------------------------
# compile - latexmk first, pdflatex x2 fallback, hard timeout, never hangs
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: Path, timeout: int) -> tuple[bool, str]:
    try:
        from laplace.manuscript import build_jobs
        owned = build_jobs.run(cmd, cwd, timeout)
        if owned is not None:
            return owned
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode == 0, (r.stdout or "") + "\n" + (r.stderr or "")
    except FileNotFoundError:
        return False, f"__MISSING__ {cmd[0]} not on PATH"
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT: {' '.join(cmd)} exceeded {timeout}s and was killed"
    except OSError as e:
        return False, f"OSError launching {cmd[0]}: {e}"


# ---------------------------------------------------------------------------
# THE LOCAL-TEX-PATH LAW (his standing instruction, 2026-07-14).  The author's
# box runs a DIFFERENT TeX toolchain path than this container (apt texlive with
# latexmk/synctex on PATH here; a Windows TeX distribution at its own location
# there).  Every TeX-tool invocation resolves PER-PLATFORM in one order: an env
# override FIRST (the LAPLACE_UV_BIN precedent — restart_reader._resolve_uv),
# then ``shutil.which``, then an HONEST ``None`` — NEVER a hardcoded path (the
# banked disease is layout_gates.DEFAULT_UV, a Linux literal that broke his box).
# When the tool is absent the feature DEGRADES HONESTLY (present:false, a reason,
# a fix naming the env var) — never a 500, never a silently-wrong jump.
# ---------------------------------------------------------------------------

def _tex_bin(name: str, env_var: str) -> str | None:
    """Resolve a TeX-toolchain binary per the local-TeX-path law: ``$<env_var>``
    (his box points this at its own toolchain), then ``shutil.which(name)`` (this
    container's PATH), then plain ``None``. Returns the first candidate that
    resolves to a real executable/file — no hardcoded final fallback, because a
    Linux literal is exactly the disease this law exists to kill."""
    import os
    for cand in (os.environ.get(env_var), shutil.which(name)):
        if not cand:
            continue
        if shutil.which(cand) or Path(cand).is_file():
            return cand
    return None


def _synctex_bin() -> str | None:
    """The ``synctex`` binary, resolved per the local-TeX-path law: env override
    ``LAPLACE_SYNCTEX_BIN`` → ``which('synctex')`` → plain ``None``. The synctex-
    follow feature (W4.2) reads this and, on ``None``, disables follow through the
    ``.hy-stale`` atom naming the env var — never a hardcoded MiKTeX/TeX Live path."""
    return _tex_bin("synctex", "LAPLACE_SYNCTEX_BIN")


def _latexmk_bin() -> str | None:
    """The ``latexmk`` binary, resolved per the local-TeX-path law: env override
    ``LAPLACE_LATEXMK_BIN`` → ``which('latexmk')`` → plain ``None``. The recompile
    gesture (W4.4) reads this and, on ``None``, REFUSES plainly (names the env var)
    instead of silently falling to pdflatex — never a hardcoded path (his box runs a
    Windows TeX distribution at its own location; the container runs apt texlive)."""
    return _tex_bin("latexmk", "LAPLACE_LATEXMK_BIN")


def _pdflatex_bin() -> str | None:
    """The ``pdflatex`` binary per the local-TeX-path law (env → which → None)."""
    return _tex_bin("pdflatex", "LAPLACE_PDFLATEX_BIN")


def _bibtex_bin() -> str | None:
    """The ``bibtex`` binary per the local-TeX-path law (env → which → None)."""
    return _tex_bin("bibtex", "LAPLACE_BIBTEX_BIN")


def _pdflatex_sequence(p: Path, cwd: Path) -> tuple[bool, str]:
    """A self-contained compile that does NOT depend on latexmk's incremental state (which
    an interrupted or lock-broken run can poison): pdflatex, then bibtex when the aux shows
    a bibliography, then two more passes to settle refs. The reliable fallback."""
    # LOCAL-TEX-PATH LAW: resolve each tool (env → which → literal name so an absent
    # tool degrades to _run's honest __MISSING__), never a hardcoded path.
    pdflatex = _pdflatex_bin() or "pdflatex"
    bibtex = _bibtex_bin() or "bibtex"
    passes: list[str] = []
    ok, o = _run([pdflatex, "-synctex=1", "-recorder", "-interaction=nonstopmode", p.name],
                 cwd, _PDFLATEX_TIMEOUT)
    passes.append(o)
    if not ok:
        return False, "\n".join(passes)
    aux = p.with_suffix(".aux")
    try:
        has_bib = aux.is_file() and "\\bibdata" in aux.read_text(encoding="utf-8", errors="replace")
    except OSError:
        has_bib = False
    if has_bib:
        ok, o = _run([bibtex, p.stem], cwd, _PDFLATEX_TIMEOUT)
        passes.append(o)
        if not ok:
            return False, "\n".join(passes)
    for _ in range(2):
        ok, o = _run([pdflatex, "-synctex=1", "-recorder", "-interaction=nonstopmode", p.name],
                     cwd, _PDFLATEX_TIMEOUT)
        passes.append(o)
        if not ok:
            return False, "\n".join(passes)
    return True, "\n".join(passes)


def compile_tex(file_param: str, *, repo_root: Path | None = None,
                _prior_status: dict[str, Any] | None = None, corpus: str = '',
                compile_root: str = '', _scope: dict | None = None) -> dict[str, Any]:
    """Compile the tex to PDF in its own directory. latexmk -pdf first; if latexmk
    is not installed, pdflatex twice (refs need the second pass). Bounded by hard
    timeouts. Returns {ok, log_tail (last 60 lines), pdf (repo-relative posix or
    None), outputs (producer identities, no bodies)} - the endpoint contract."""
    p = _safe_path(file_param, repo_root)
    if p is None:
        return {"ok": False, "log_tail": "path outside repo root (refused)", "pdf": None}
    if not p.is_file():
        return {"ok": False, "log_tail": f"no such tex file: {file_param}", "pdf": None}
    scope = _scope or _compile_scope(p, corpus=corpus, compile_root=compile_root, repo_root=repo_root)
    p = scope['root']            # a fragment compiles its declared paper
    cwd = p.parent
    active_root = (repo_root or _repo_root()).resolve()
    prior = _read_recompile_status(p) if _prior_status is None else _prior_status
    from laplace.manuscript import tex_dependencies
    output_proof = _build_output_currentness(p, active_root, prior.get("outputs"))
    output_trusted = prior.get("state") == "done" and prior.get("ok") is True and output_proof["current"]
    inputs_current = (isinstance(prior.get("dependencies"), dict) and
                      not tex_dependencies.changed(prior["dependencies"], active_root))
    trusted = output_trusted and inputs_current
    # Output drift/legacy needs a producer repair. Ordinary changed inputs keep
    # latexmk's dependency-driven rebuild; an ungrounded no-op gets one forced run.
    force = not output_trusted
    repaired = []
    # Only artifacts identified by a previous successful producer are eligible
    # for repair cleanup. Never derive deletion authority from a changed aux.
    generated = ((prior.get("outputs") or {}).get("generated") or
                 prior.get("generated_outputs") or [])
    repair_aux = force and (not output_proof["current"]) and (
        output_proof["state"] != "CHANGED" or bool(set(generated) & set(output_proof["changes"])))
    if repair_aux:
        for name in generated:
            relative = Path(name)
            artifact = active_root / relative
            if (not relative.is_absolute() and ".." not in relative.parts and
                    artifact.parent.resolve().is_relative_to(active_root) and
                    (artifact.suffix in {".aux", ".bbl", ".bcf"} or artifact.name.endswith(".run.xml"))):
                try:
                    artifact.unlink()
                    repaired.append(name)
                except FileNotFoundError:
                    pass
    fallback = False
    before_pdf = p.with_suffix(".pdf").stat() if p.with_suffix(".pdf").is_file() else None
    t0 = time.time()             # success is a FRESH pdf written after this, not exit code
    # -synctex=1: the review mode's click->source anchor rides the .synctex.gz.
    # The pdf WRITE contends with a concurrent reader (pdftoppm rendering the review
    # pages, or a viewer tab): on Windows that reader holds a share-lock, and the
    # write fails with a sharing violation ("can't write on file main.pdf") - NOT a
    # LaTeX error. The lock is sub-second, so retry the compile a few times before
    # giving up, so a render in flight never makes a compile "fail" (his 2026-07-03).
    latexmk = _latexmk_bin() or "latexmk"        # LOCAL-TEX-PATH LAW (env → which → literal)
    for _attempt in range(4):
        ok, out = _run([latexmk, *(["-g"] if force else []), "-pdf", "-synctex=1", "-recorder", "-interaction=nonstopmode",
                        "-halt-on-error", p.name], cwd, _LATEXMK_TIMEOUT)
        if out.startswith("__MISSING__") or not ok:
            # latexmk absent OR its incremental state failed (a poisoned .fdb from an
            # interrupted run). Drop that db so latexmk can recover next time, and this
            # time rebuild with the self-contained pdflatex sequence, which always works.
            if not out.startswith("__MISSING__"):
                try:
                    p.with_suffix(".fdb_latexmk").unlink()
                except OSError:
                    pass
            fallback = True
            ok, out = _pdflatex_sequence(p, cwd)
        low = out.lower()
        if ok and not force and not trusted and ("nothing to do" in low or "up-to-date" in low):
            try:
                after_run = p.with_suffix(".pdf").stat()
                untouched = before_pdf is not None and all(
                    getattr(before_pdf, key) == getattr(after_run, key)
                    for key in ("st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"))
            except OSError:
                untouched = True
            if untouched:
                force = True
                continue
        pdf_locked = "can't write on file" in low or "permission denied" in low
        if ok or not pdf_locked or _attempt == 3:
            break
        time.sleep(0.5)                                # let the concurrent reader finish
    pdf = p.with_suffix(".pdf")
    # Forced repair must actually write the PDF; a recent preexisting PDF plus
    # "Nothing to do" is not producer evidence. A verified no-op is rechecked.
    try:
        after_pdf = pdf.stat()
        rewritten = before_pdf is None or any(getattr(before_pdf, key) != getattr(after_pdf, key)
                                              for key in ("st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"))
        fresh_pdf = rewritten and after_pdf.st_mtime >= t0 - 1.0
    except OSError:
        fresh_pdf = False
    low = out.lower()
    no_op = "nothing to do" in low or "up-to-date" in low
    verified_no_op = (trusted and no_op and
                     _build_output_currentness(p, active_root, prior.get("outputs"))["current"] and
                     not tex_dependencies.changed(prior["dependencies"], active_root))
    ok = bool(ok and (fresh_pdf or verified_no_op) and pdf.is_file() and _synctex_fresh(pdf))
    tail = "\n".join(out.splitlines()[-60:])
    if repaired:
        tail = "Regenerated owned auxiliaries: " + ", ".join(repaired) + "\n" + tail
    pdf_rel = None
    if ok:
        try:
            pdf_rel = pdf.relative_to((repo_root or _repo_root()).resolve()).as_posix()
        except ValueError:
            pdf_rel = str(pdf)
    return {"ok": ok, "log_tail": tail, "pdf": pdf_rel,
            "outputs": _build_output_snapshot(p, active_root, generated_bib=fallback) if ok else None}


# ---------------------------------------------------------------------------
# W8 — THE EDITOR-SAVE STORE (J4): changed editor saves BANK a version.
#
# A small per-project store next to the manuscript — ``<manuscript_dir>/editor_saves/
# <version_id>/`` holding the saved file's bytes + a ``VERSION.json`` ``{ts, author,
# surface, file, sha, version_id, source}``. It MIRRORS the ``versions/`` SNAPSHOT.json
# shape (candidate_lock.snapshot_incumbent is the larger sibling) at a smaller grain —
# NOT a second ledger idiom. The rows join the ONE version rail (shared_ui.versions_join
# reads this store; the artefact rail renders them, diffable + restorable).
#
# BANKING IS OPT-IN: a changed ``POST /projection/tex`` carrying ``?bank=`` mints a
# version. Ordinary unchanged Save validates its source guard and acknowledges
# without rewriting, banking or attributing another occurrence. The editor pane
# opts in (``bank=editor``); that flag is not a separate archival request. Explicit
# archive calls and RESTORE remain deliberate occurrences, even for equal bytes.
#
# BOUNDED (the golden law, at store grain): the last ``_EDITOR_SAVES_KEEP`` saves are kept;
# the oldest are pruned and recorded LOUDLY in ``index.json``'s ``dropped`` list — never a
# silent drop.
# ---------------------------------------------------------------------------

_EDITOR_SAVES_DIRNAME = "editor_saves"
_EDITOR_SAVES_KEEP = 32
_EDITOR_SAVE_INDEX_FIELDS = ('version_id', 'ts', 'author', 'surface', 'file', 'sha',
                             'source', 'source_file', 'bytes')
#: a version_id / store segment: a plain name, never a traversal shape.
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")

#: A3 — THE LOCK: the index read-modify-write + id mint + dir write is ONE critical
#: section, guarded the SAME nested idiom as project_creation._append_shared_rows (read it) — a
#: process-local threading.Lock() (so two threads of THIS process never both "hold" the
#: per-path OS-level filelock below; fcntl locks are per-process) nested in a per-
#: manuscript-dir filelock beside index.json. Without it, two concurrent banks race the
#: read-modify-write and the judge's contention hammer (2 threads x 20 reps) lost rows /
#: minted duplicate ids. One process-wide lock (not per-md) mirrors dashboard.py's own
#: coarse single-lock idiom — editor saves are low-frequency, so the simplicity is earned.
_EDITOR_SAVES_WRITE_LOCK = threading.Lock()




def _rel_to_root(p: Path) -> str:
    """A repo-relative POSIX path, or the absolute string for a path outside the root
    (never a silent lie) — the mechanism reused by compile_tex, factored to one place."""
    try:
        return p.resolve().relative_to(_repo_root().resolve()).as_posix()
    except ValueError:
        return str(p)


def _manuscript_dir_for(corpus: str) -> Path | None:
    """The manuscript dir a project banks its editor-saves under — the one
    server-canonical resolution (``registry.project_context``), so the store a save
    WRITES is the SAME store the version rail (``shared_ui.versions_join``) READS.
    ``None`` for an unknown / path-shaped corpus (the registry fence)."""
    if not corpus:
        return None
    try:
        from laplace.pipeline import registry
        ctx = registry.project_context(corpus, _repo_root())
    except Exception:  # noqa: BLE001 — a resolver hiccup degrades to no store, never a crash
        return None
    if ctx is None or ctx.manuscript_dir is None:
        return None
    return ctx.storage_dir


def _editor_saves_dir(md: Path) -> Path:
    return md / _EDITOR_SAVES_DIRNAME


def _load_saves_index(md: Path) -> dict:
    p = _editor_saves_dir(md) / "index.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("saves", [])
            data.setdefault("dropped", [])
            data.setdefault("seq", 0)   # A2 — the monotonic mint counter (below)
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"saves": [], "dropped": [], "seq": 0}


def _write_saves_index(md: Path, index: dict) -> None:
    d = _editor_saves_dir(md)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "index.json.tmp"
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(d / "index.json")


def _editor_saves_lockfile(md: Path) -> Path:
    return _editor_saves_dir(md) / "index.json.lock"   # *.lock — gitignored, never content


def _next_version_id(index: dict) -> str:
    """A sortable, COLLISION-FREE save id: ``save-YYYY-MM-DD_HHMMSS-<seq>`` (candidate_lock's
    ts dialect + a monotonic suffix). Uniqueness rides ``index['seq']`` — a counter
    persisted in index.json and incremented on EVERY mint (never derived from what
    happens to exist on disk).

    A2 — Monotonic id mint: the prior scheme derived the ``-N`` suffix from a
    ``while (dir).exists()`` probe, so a name freed by pruning became "available" again —
    a same-second burst past the 32-bound could re-mint an id already retired into
    ``index['dropped']`` (the judge's live proof: one id present in BOTH ``dropped[]`` and
    ``saves[]``). A counter that only ever climbs, persisted alongside the ledger it
    protects, can never repeat regardless of what prune erases — mint and prune both live
    inside the one locked critical section (:func:`bank_editor_save`), so the counter and
    the ledger it stamps can never drift apart."""
    index["seq"] = int(index.get("seq", 0)) + 1
    return "save-" + time.strftime("%Y-%m-%d_%H%M%S", time.gmtime()) + "-" + str(index["seq"])


def _prune_editor_saves(md: Path, index: dict) -> None:
    """Keep the newest ``_EDITOR_SAVES_KEEP`` saves; shed the oldest LOUDLY into
    ``index['dropped']`` (dir removed, id + reason recorded) — never a silent drop."""
    saves = index.get("saves", [])
    while len(saves) > _EDITOR_SAVES_KEEP:
        old = saves.pop(0)
        vid = old.get("version_id")
        if not vid:
            continue
        try:
            shutil.rmtree(_editor_saves_dir(md) / vid)
        except OSError:
            pass
        index.setdefault("dropped", []).append(
            {"version_id": vid, "ts": old.get("ts"), "dropped_ts": observe.now_iso(),
             "reason": f"bounded store: kept the newest {_EDITOR_SAVES_KEEP} saves"})


def bank_editor_save(md: Path, live_file: Path, data: bytes, *, author: str,
                     surface: str, source: str = "save") -> dict:
    """Bank one editor save into ``<md>/editor_saves/<version_id>/`` — the saved bytes
    (basename preserved) + a ``VERSION.json`` manifest. Prunes to the bounded store and
    updates ``index.json``. Returns the manifest (carrying the minted ``version_id``).

    A3 — THE LOCK: the index read-modify-write, the id mint, and the dir write are ONE
    critical section — a process-local :data:`_EDITOR_SAVES_WRITE_LOCK` nested in an
    OS-level filelock beside ``index.json`` (the project_creation._append_shared_rows idiom),
    so two concurrent banks can never race the read-modify-write into a lost row or a
    duplicate-minted id (the A2 counter and the ledger it stamps are read, bumped, and
    written back without any other bank able to interleave)."""
    from filelock import FileLock
    d = _editor_saves_dir(md)
    d.mkdir(parents=True, exist_ok=True)
    fname = live_file.name
    sha = hashlib.sha256(data).hexdigest()
    with _EDITOR_SAVES_WRITE_LOCK:
        with FileLock(str(_editor_saves_lockfile(md)), timeout=30):
            index = _load_saves_index(md)
            vid = _next_version_id(index)          # A2 — mints AND bumps index['seq']
            dest = d / vid
            dest.mkdir(parents=True, exist_ok=True)
            (dest / fname).write_bytes(data)
            manifest = {
                "version_id": vid, "ts": observe.now_iso(), "author": author or "author",
                "surface": surface or "editor", "file": fname,
                "sha": sha, "source": source, "bytes": len(data),
                "source_file": _rel_to_root(live_file.resolve() if live_file.is_absolute() else (md / live_file).resolve()),
            }
            (dest / "VERSION.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
            index["saves"].append({k: manifest[k] for k in _EDITOR_SAVE_INDEX_FIELDS})
            _prune_editor_saves(md, index)
            _write_saves_index(md, index)
    return manifest


def latest_editor_save(md: Path) -> dict | None:
    """The most recent banked editor-save row (index order), or ``None``."""
    saves = _load_saves_index(md).get("saves", [])
    return saves[-1] if saves else None


def _source_observation(path: Path, *, repo_root=None, query=None, access=None) -> dict:
    """Same physical source owner for full editor buffers and guarded native parts."""
    data = path.read_bytes();text=data.decode('utf-8', errors='replace')
    revision="sha256:"+hashlib.sha256(data).hexdigest()
    file=path.relative_to(Path(repo_root).resolve()).as_posix() if repo_root is not None else _rel_to_root(path)
    result={"schema_version":"laplace.projection-source/1","file":file,"content":text,"expected_source_digest":revision}
    if query and ('offset' in query or 'limit' in query):
        guards=query.get('guards')
        if guards and (guards['source_revision']!=revision or not access or guards['selection_identity']!=access['selection_identity']):
            raise ValueError('CHANGED_INPUT: exact physical source part basis changed; inspect the source again.')
        from laplace.manuscript.reconciliation import _text_part
        offset=query.get('offset',0);chunk,end=_text_part(text,offset,query.get('limit',4096))
        result.update(chunk)
        result['line_start']=text.encode()[:offset].decode().count('\n')+1
        result['line_end']=result['line_start']+chunk['content'].count('\n')
        if chunk['coverage']['has_more']:
            from urllib.parse import urlencode
            from laplace.core import grammar
            next_query={**query,'offset':end,'guards':{'source_revision':revision,'selection_identity':access['selection_identity']}}
            result['next_read']={
                'native_request':{'verb':'read','concept':'source-file@paragraph','target':query['corpus']+'::'+file,'expected':[],
                    'payload':grammar.to_payload(next_query),'by':''},
                'http':{'method':'GET','url':'/projection/tex?'+urlencode({key:json.dumps(value,separators=(',',':')) if isinstance(value,dict) else value for key,value in next_query.items()})}}
        result['read_instruction']='Exact UTF8 bytes. complete means the whole file is here; at_end/has_more ends continuation. Each next_read pins the same source/selection.'
    return result


def _source_guard(path: Path, expected: str | None) -> dict | None:
    observed = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    if not isinstance(expected, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected) or expected != observed:
        return {"error": "Source changed or no exact inspected source guard was supplied. Inspect this file again; your draft was not saved.",
                "status": 409, "reason": "source-revision-conflict", "current_source_digest": observed,
                "recovery": {"method": "GET", "route": "/projection/tex",
                             "query": {"file": _rel_to_root(path), "view": "source"}}}
    return None


def _replace_source(path: Path, data: bytes) -> None:
    """Atomic source publication inside the caller's physical lease."""
    from laplace.manuscript.source_effects import replace
    replace(path, data)


def read_editor_save(md: Path, version_id: str, *, repo_root: Path | None = None,
                     read_body: bool = True) -> dict:
    """One exact version/target/body resolver for the rail, detail and restore.

    Metadata-only rail reads never assert body verification. A basename-only
    historical save remains inspectable, with its live binding unproved.
    """
    root = (repo_root or _repo_root()).resolve()
    if not isinstance(version_id, str) or not _SEGMENT_RE.fullmatch(version_id):
        raise ValueError("saved version identity must be one store segment")
    directory = _editor_saves_dir(md) / version_id
    if not directory.resolve().is_relative_to(_editor_saves_dir(md).resolve()):
        raise ValueError("saved version escapes its archive store")
    manifest = json.loads((directory / "VERSION.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("version_id") != version_id:
        raise ValueError("saved version metadata does not match its selected identity")
    file = manifest.get("file")
    if not isinstance(file, str) or not file or Path(file).name != file or "\\" in file or file in {".", ".."}:
        raise ValueError("saved file identity is invalid")
    saved = (directory / file).resolve()
    if saved.parent != directory.resolve():
        raise ValueError("saved file escapes its exact version")
    target = manifest.get("source_file")
    live = None
    if target is not None:
        if not isinstance(target, str) or not target:
            raise ValueError("saved source target must be a path")
        from laplace.projects.writing_portability import source_path
        live = source_path(target, root)
        if not live.is_relative_to(root):
            raise ValueError("saved source target escapes the active checkout")
    data = None
    size, sha = manifest.get("bytes"), manifest.get("sha")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0 or not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha):
        raise ValueError("saved source body identity is invalid")
    if read_body:
        # New occurrences retain their target/body identity independently in
        # the existing index. Detail and Restore cannot trust a changed VERSION
        # while the rail refuses it. Old missing pins are never reconstructed.
        indexed = _load_saves_index(md).get('saves')
        if not isinstance(indexed, list):
            raise ValueError('saved occurrence index is unavailable')
        occurrences = [row for row in indexed
                       if isinstance(row, dict) and row.get('version_id') == version_id]
        if len(occurrences) > 1:
            raise ValueError('saved occurrence identity is ambiguous')
        if occurrences and any(key in occurrences[0] for key in ('source_file', 'bytes')):
            occurrence = occurrences[0]
            if (type(occurrence.get('bytes')) is not int or occurrence['bytes'] < 0 or
                    any(key not in occurrence or occurrence[key] != manifest.get(key)
                        for key in _EDITOR_SAVE_INDEX_FIELDS)):
                raise ValueError('saved occurrence identity does not match its recorded pins')
        data = saved.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha or len(data) != size:
            raise ValueError("saved source body does not match its recorded identity")
    return {"manifest":manifest, "saved_file":saved, "live_file":live, "data":data,
            "source_binding":"BOUND" if live is not None else "UNPROVED",
            "body_status":"VERIFIED" if read_body else "NOT_OBSERVED"}



def restore_editor_save(corpus: str, file_param: str, version_id: str,
                        expected_source_digest: str | None = None, expected_selection: str | None = None) -> dict:
    """RESTORE a banked editor-save back into the live file THROUGH the SAME banking
    save path — so a restore is a NEW save (never a rewind: the rail grows a row and the
    ``restored_from`` is recorded). Returns ``{ok, restored_from, version_id, file, bytes}``
    or ``{error, status}`` (fenced: the live file resolves in-repo, the version_id is a
    plain store segment). The saved version/file/body and independently inspected
    current live digest are separate guards; historical identity never substitutes
    for a current-target observation."""
    live = _safe_path(file_param)
    if live is None:
        return {"error": "file must resolve inside the repo root", "status": 403}
    from laplace.manuscript import manuscript_source
    from laplace.pipeline import registry
    if registry.resolve(corpus, _repo_root()) is not None and manuscript_source.resolve(corpus, _repo_root(), include_candidates=False).get('read_only'):
        try:
            manuscript_source.source_access(corpus, live, _repo_root(), writable=True, expected_selection=expected_selection)
        except manuscript_source.SourceAccessError as exc:
            return dict(exc.response)
    md = _manuscript_dir_for(corpus)
    if md is None:
        return {"error": f"no manuscript store for corpus {corpus!r} (restore needs it)",
                "status": 404}
    if not version_id or not _SEGMENT_RE.match(version_id):
        return {"error": "version_id must be a plain store segment", "status": 400}
    snap = _editor_saves_dir(md) / version_id
    man_p = snap / "VERSION.json"
    if not man_p.is_file():
        # A4 — THE PRUNED 404 NAMES THE DROP: a version_id retired into index['dropped']
        # (the bounded store shed it) reads DISTINCT from one that never existed — the
        # body names the bound, when it was dropped, and why, so a stale restore link
        # explains itself instead of reading as a generic 404.
        dropped = _load_saves_index(md).get("dropped", [])
        rec = next((r for r in dropped if r.get("version_id") == version_id), None)
        if rec is not None:
            return {"error": (f"save {version_id!r} was dropped by the "
                              f"{_EDITOR_SAVES_KEEP}-bound at {rec.get('dropped_ts')} "
                              f"({rec.get('reason')}) — not restorable, distinct from "
                              "never having existed"),
                    "status": 404, "dropped": rec}
        return {"error": f"no banked save {version_id!r}", "status": 404}
    try:
        observed = read_editor_save(md, version_id)
        manifest, data = observed['manifest'], observed['data']
        if observed['source_binding'] != 'BOUND':
            return {"error":"Legacy saved version has no exact source target binding; inspect its preserved snapshot.",
                    "status":409, "reason":"saved-source-target-unproved"}
        if observed['live_file'] != live:
            raise ValueError("selected saved version belongs to another source file")
    except ValueError as e:
        return {"error": f"banked save identity unproved: {e}", "status": 409,
                "reason": "saved-source-identity-unproved"}
    except OSError as e:
        return {"error": f"banked save unreadable: {e}", "status": 500}
    # write the banked bytes back to the live file, THEN bank a new version (restore-is-a-save).
    from laplace.manuscript import manuscript_source
    from laplace.pipeline import registry
    from contextlib import nullcontext
    scoped = registry.resolve(corpus, _repo_root()) is not None
    try:
        with (manuscript_source.selection_mutation(corpus, _repo_root()) if scoped else nullcontext()), manuscript_source.source_mutation([live]):
            access = manuscript_source.source_access(corpus, live, _repo_root(), writable=True, expected_selection=expected_selection) if scoped else None
            conflict = _source_guard(live, expected_source_digest)
            if conflict: return conflict
            before = live.read_bytes()
            if before != data:
                _replace_source(live, data)
            from laplace.manuscript import source_effects
            effect = source_effects.receipt(corpus, access['selection_identity'] if access else None,
                [source_effects.observed_file(_repo_root(), live, before, data)])
            result = {"ok": True, "source_committed": True, "restored_from": version_id,
                      "file": _rel_to_root(live), "bytes": len(data),
                      "consumed_source_digest": expected_source_digest,
                      "expected_source_digest": "sha256:" + hashlib.sha256(data).hexdigest()}
            try:
                new = bank_editor_save(md, live, data, author=manifest.get("author") or "author",
                                       surface="restore", source=f"restore:{version_id}")
                result["version_id"] = new["version_id"]
            except Exception as exc:
                result["snapshot_status"] = "UNPROVED"
                _source_maintenance_warning(result, "bank_editor_save", exc)
            if access:
                result['selection_identity'] = access['selection_identity']
                result['invalidated'] = ['manuscript','document','template-preview']
    except manuscript_source.SourceAccessError as exc:
        return dict(exc.response)
    except manuscript_source.SourceLeaseError as exc:
        return {"error": str(exc), "status": 409, "reason": "source-lease-unavailable"}
    result.update(source_effects.raw_compatibility(effect))
    source_effects.finish(result, corpus, _repo_root(), effect, changes=[(live, before, data)])
    return result


def stamp_compile(res: dict, corpus: str) -> dict:
    """Record WHICH banked editor-save a compile built: stamp the LATEST save's
    version_id into the compile response and a ``compile.json`` sidecar under the store
    (``{version_id, ts, ok, pdf}`` — the plain minimal the rail can join). A project with
    no editor-saves stamps nothing (the key is additive; ``res`` returns unchanged)."""
    if not isinstance(res, dict):
        return res
    md = _manuscript_dir_for(corpus)
    if md is None:
        return res
    latest = latest_editor_save(md)
    if latest is None:
        return res
    vid = latest.get("version_id")
    res["built_version_id"] = vid
    sidecar = {"version_id": vid, "ts": observe.now_iso(),
               "ok": bool(res.get("ok")), "pdf": res.get("pdf")}
    try:
        d = _editor_saves_dir(md)
        d.mkdir(parents=True, exist_ok=True)
        (d / "compile.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return res


# ---------------------------------------------------------------------------
# OFFLINE TOOLING - NOT a serving path (W4.3)
# ---------------------------------------------------------------------------
# The viewer's serving surface renders the pdf with pdf.js (client-side) and builds its
# selectable text layer from pdf.js getTextContent; the PNG raster + poppler routes are
# retired (see _RETIRED_PNG / _RETIRED_TEXTLAYER, handle()). The functions below survive
# ONLY as importable tooling for the FROZEN export scripts (scripts/export_review.py,
# scripts/build_review_bundle.py - both shelved 2026-07-08) and the offline lock reader
# (readers/restart_reader.py, via _poppler_pdftotext). They MUST NOT be called from
# handle(); the grep-guard in tests/test_w4_3_pdfjs_text_layer.py enforces that no
# serving route reaches pdftoppm/poppler.
_PAGES_DPI = 150
_PAGES_DIRNAME = "_pv_pages"      # gitignored render cache beside the pdf
_PDFTOPPM_TIMEOUT = 180
_SYNCTEX_TIMEOUT = 20


def _pages_dir(pdf: Path) -> Path:
    return pdf.parent / _PAGES_DIRNAME


def _synctex_fresh(pdf: Path) -> bool:
    """The pipeline invariant: main.synctex.gz must correspond to THIS main.pdf.

    Hover provenance and every comment anchor read synctex; if the pdf is replaced
    without a matching synctex (a hand-copied pdf, a partial compile, a jobname trick),
    the anchor resolves to nothing and the review surface silently serves blank "?".
    The one authoritative producer is compile_tex (native jobname + -synctex=1), which
    writes both together; this checks they are in lockstep so a desync becomes a loud,
    self-healable signal instead of a silent bug (his 2026-07-03: don't let it go stale)."""
    try:
        pmt = pdf.stat().st_mtime
    except OSError:
        return False
    for cand in (pdf.with_suffix(".synctex.gz"), pdf.with_suffix(".synctex")):
        try:
            if cand.is_file() and cand.stat().st_mtime >= pmt - 1.0:
                return True
        except OSError:
            continue
    return False


def render_pages(file_param: str, *, corpus: str = '', compile_root: str = '') -> dict[str, Any]:
    """Render the paper's pages to PNGs (pdftoppm, cached by pdf mtime) - the
    review mode's canvas. Returns {n_pages, dpi, pages:[repo-relative]}. The
    cache invalidates when the pdf changes, so a recompile refreshes the view."""
    p = _safe_path(file_param)
    if p is None:
        return {"error": "file must resolve inside the repo root"}
    pdf = resolve_root(p, corpus=corpus, compile_root=compile_root).with_suffix(".pdf") if p.suffix.lower() == ".tex" else p
    if not pdf.is_file():
        return {"error": f"no compiled pdf at {pdf.name} - compile first"}
    d = _pages_dir(pdf)
    stamp = d / ".stamp"
    want = f"{pdf.stat().st_mtime_ns}:{_PAGES_DPI}"
    if not (stamp.is_file() and stamp.read_text() == want and any(d.glob("page-*.png"))):
        d.mkdir(exist_ok=True)
        for old in d.glob("page-*.png"):
            old.unlink()
        ok, out = _run(["pdftoppm", "-r", str(_PAGES_DPI), "-png", pdf.name,
                        str(d / "page")], pdf.parent, _PDFTOPPM_TIMEOUT)
        if not ok and not any(d.glob("page-*.png")):
            return {"error": "pdftoppm failed", "log_tail": out[-800:]}
        stamp.write_text(want)
    rr = _repo_root().resolve()
    pages = sorted(d.glob("page-*.png"))
    return {"n_pages": len(pages), "dpi": _PAGES_DPI,
            "synctex_fresh": _synctex_fresh(pdf),   # the review surface self-heals when False
            "pages": [q.relative_to(rr).as_posix() for q in pages]}


def pdf_info(file_param: str, *, corpus: str = '', compile_root: str = '') -> dict[str, Any]:
    """The light metadata the pdf.js render path needs: whether a compiled pdf exists and
    whether its synctex is in lockstep (the self-heal signal), without touching any raster
    cache. The client renders pages itself from /projection/pdf (W4.3: pdf.js is the one
    render path on the serving surface; there is no PNG fallback route left to fall to)."""
    p = _safe_path(file_param)
    if p is None:
        return {"error": "file must resolve inside the repo root"}
    scope = _compile_scope(p, corpus=corpus, compile_root=compile_root) if p.suffix.lower() == '.tex' or corpus or compile_root else None
    pdf = scope['root'].with_suffix('.pdf') if scope else p
    if p.suffix.lower() == '.pdf' and scope and p != pdf:
        raise CompileRootRefused('The requested PDF is not the selected root output.', 'compile-root-output-unproved', corpus=corpus)
    if not pdf.is_file():
        return {"error": f"no compiled pdf at {pdf.name} - compile first"}
    rr = _repo_root().resolve()
    try:
        scope = scope or _compile_scope(p, corpus=corpus, compile_root=compile_root)
        fresh, reason = _follow_fresh(pdf, scope['root'], _scope=scope)
    except CompileRootRefused as refused:
        fresh, reason = False, str(refused)
    return {"ok": True, "pdf": pdf.relative_to(rr).as_posix(),
            "mtime_ns": pdf.stat().st_mtime_ns,
            "synctex_fresh": fresh, "synctex_reason": reason or None}


_POPPLER_CACHE: dict[str, str | None] = {}


def _poppler_pdftotext() -> str | None:
    """A pdftotext that supports ``-bbox`` (poppler, NOT xpdf). The default on PATH may
    be xpdf's build, which has no ``-bbox``; poppler ships alongside pdftoppm and inside
    MiKTeX. Probe candidates by version string, cache the winner (or None)."""
    if "path" in _POPPLER_CACHE:
        return _POPPLER_CACHE["path"]
    cands: list[str] = []
    for name in ("pdftotext",):
        w = shutil.which(name)
        if w:
            cands.append(w)
    ppm = shutil.which("pdftoppm")               # the poppler sibling render already uses
    if ppm:
        cands.append(str(Path(ppm).with_name("pdftotext")))
    import os
    cands += [str(q) for q in Path(os.path.expanduser("~")).glob(
        "AppData/Local/Programs/MiKTeX/miktex/bin/*/pdftotext.exe")]
    for c in cands:
        try:
            r = subprocess.run([c, "-v"], capture_output=True, encoding="utf-8",
                               errors="replace", timeout=10)
            if "poppler" in ((r.stdout or "") + (r.stderr or "")).lower():
                _POPPLER_CACHE["path"] = c
                return c
        except (OSError, subprocess.TimeoutExpired):
            continue
    _POPPLER_CACHE["path"] = None
    return None


_WORD_RE = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>')
_PAGE_RE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', re.S)


def text_layer(file_param: str, *, corpus: str = '', compile_root: str = '') -> dict[str, Any]:
    """The SELECTABLE text layer for review mode: per-page word boxes (poppler
    ``pdftotext -bbox``), so a comment anchors to a highlighted SPAN or a figure
    region, not a pixel on a screenshot. Each word carries its box in PDF points
    (top-left origin, the same space synctex_anchor consumes), in reading order, so
    the browser's native selection flows word to word. Cached beside the pdf by mtime,
    like render_pages - a recompile refreshes both."""
    p = _safe_path(file_param)
    if p is None:
        return {"error": "file must resolve inside the repo root"}
    pdf = resolve_root(p, corpus=corpus, compile_root=compile_root).with_suffix(".pdf") if p.suffix.lower() == ".tex" else p
    if not pdf.is_file():
        return {"error": f"no compiled pdf at {pdf.name} - compile first", "pages": []}
    exe = _poppler_pdftotext()
    if not exe:
        return {"error": "no poppler pdftotext (-bbox) on this machine", "pages": []}
    cache = _pages_dir(pdf) / ".textlayer.json"
    want = str(pdf.stat().st_mtime_ns)
    if cache.is_file():
        try:
            j = json.loads(cache.read_text(encoding="utf-8"))
            if j.get("stamp") == want:
                return {"pages": j["pages"]}
        except (OSError, json.JSONDecodeError):
            pass
    with tempfile.TemporaryDirectory() as td:
        outp = Path(td) / "tl.html"
        _run([exe, "-bbox", pdf.name, str(outp)], pdf.parent, _PDFTOPPM_TIMEOUT)
        if not outp.is_file():
            return {"error": "pdftotext -bbox produced no output", "pages": []}
        xml = outp.read_text(encoding="utf-8", errors="replace")
    pages: list[dict[str, Any]] = []
    for pg in _PAGE_RE.finditer(xml):
        w, h = float(pg.group(1)), float(pg.group(2))
        words = [[round(float(m.group(1)), 1), round(float(m.group(2)), 1),
                  round(float(m.group(3)), 1), round(float(m.group(4)), 1),
                  _html.unescape(m.group(5))]
                 for m in _WORD_RE.finditer(pg.group(3))]
        pages.append({"w": w, "h": h, "words": words})
    _pages_dir(pdf).mkdir(exist_ok=True)
    try:
        cache.write_text(json.dumps({"stamp": want, "pages": pages}), encoding="utf-8")
    except OSError:
        pass
    return {"pages": pages}


def synctex_anchor(file_param: str, page: int, x: float, y: float, *, corpus: str = '', compile_root: str = '') -> dict[str, Any]:
    """Resolve a click on the rendered pdf back to its SOURCE - the anchor chain
    of the review mode: (page, x, y in PDF points, top-left origin) -> synctex
    edit -> fragment file + line -> the provenance span holding that line ->
    its section + nodes. Every hop is the mechanism the viewer already trusts."""
    p = _safe_path(file_param)
    if p is None:
        return {"error": "file must resolve inside the repo root"}
    binary = _synctex_bin()
    if binary is None:                              # the LOCAL-TEX-PATH LAW: honest absent,
        return {"error": "synctex binary not found - set LAPLACE_SYNCTEX_BIN or install synctex",
                "absent": True,                     # checked BEFORE the pdf so a toolless box
                "reason": "the synctex binary is not on PATH and $LAPLACE_SYNCTEX_BIN is unset",
                "fix": "set LAPLACE_SYNCTEX_BIN to your TeX distribution's synctex, or install synctex"}
    scope = _compile_scope(p, corpus=corpus, compile_root=compile_root)
    pdf = scope['root'].with_suffix('.pdf')
    if not pdf.is_file():                           # gets the env-var answer, not a pdf complaint
        return {"error": f"no compiled pdf at {pdf.name}"}
    fresh, reason = _follow_fresh(pdf, scope['root'], _scope=scope)
    if not fresh:
        return {"error": reason,
                "stale": True}
    ok, out = _run([binary, "edit", "-o", f"{int(page)}:{x:.2f}:{y:.2f}:{pdf.name}"],
                   pdf.parent, _SYNCTEX_TIMEOUT)
    src, line = "", 0
    for ln in out.splitlines():
        if ln.startswith("Input:") and not src:
            src = ln[len("Input:"):].strip()
        elif ln.startswith("Line:") and not line:
            try:
                line = int(ln[len("Line:"):].strip())
            except ValueError:
                pass
    if not src or not line:
        return {"error": "synctex could not resolve this position",
                "log_tail": out[-400:]}
    rr = _repo_root().resolve()
    try:
        source = Path(src) if Path(src).is_absolute() else pdf.parent / src
        source = source.resolve()
        rel = source.relative_to(rr).as_posix()
    except (OSError, ValueError):
        return {"error": f"synctex source outside the repo: {src}"}
    if rel not in scope['tree']['files']:
        return {"error":"SyncTeX returned a source outside the selected include tree", "reason":"compile-root-membership-unproved"}
    span = next((s for s in load_map(source)
                 if s["start_line"] <= line <= s["end_line"]), None)
    para = next((s for s in load_paragraphs(source)
                 if s["start_line"] <= line <= s["end_line"]), None)
    return {"file": rel, "line": line,
            "section": (span or {}).get("section", ""),
            "nodes": (span or {}).get("nodes", []),
            "spec_id": (para or {}).get("spec_id", ""),
            "spec_ids": (para or {}).get("spec_ids", [])}


def synctex_locate(file_param: str, section: str, line: int = 0, *, corpus: str = '', compile_root: str = '') -> dict[str, Any]:
    """SOURCE -> PDF, the inverse hop: where a section (or an explicit fragment
    line) sits in the compiled pdf, via ``synctex view``. This is what lets a
    ledger comment that carries only ``{section}`` (the judge flags, the node
    comments) JUMP to its place on the page (his ask, 2026-07-08: comments
    must take me to them). Returns {page, x, y} in PDF points, top-left origin."""
    p = _safe_path(file_param)
    if p is None:
        return {"error": "file must resolve inside the repo root"}
    binary = _synctex_bin()
    if binary is None:                              # the LOCAL-TEX-PATH LAW: honest absent,
        return {"error": "synctex binary not found - set LAPLACE_SYNCTEX_BIN or install synctex",
                "absent": True,                     # checked BEFORE the pdf so a toolless box
                "reason": "the synctex binary is not on PATH and $LAPLACE_SYNCTEX_BIN is unset",
                "fix": "set LAPLACE_SYNCTEX_BIN to your TeX distribution's synctex, or install synctex"}
    scope = _compile_scope(p, corpus=corpus, compile_root=compile_root)
    root = scope['root']; pdf = root.with_suffix('.pdf')
    if not pdf.is_file():                           # gets the env-var answer, not a pdf complaint
        return {"error": f"no compiled pdf at {pdf.name}"}
    fresh, reason = _follow_fresh(pdf, root, _scope=scope)
    if not fresh:
        return {"error": reason,
                "stale": True}
    # section wins when given (the ledger-comment jump). Otherwise, if the caller
    # passed a real FRAGMENT (not the paper root), locate the line in THAT fragment
    # directly — the W4.2 cursor-follow path resolves (active fragment, caret line).
    if section:
        frag = _frag_path(root.parent, section)
    elif p.suffix.lower() == ".tex" and p.is_file():
        frag = p
    else:
        frag = root
    if frag is None or not frag.is_file():
        return {"error": f"no fragment for section {section!r}"}
    if frag.resolve().relative_to(_repo_root().resolve()).as_posix() not in scope['tree']['files']:
        return {"error":"The requested section source is not in the selected include tree", "reason":"compile-root-membership-unproved"}
    if not line:
        spans = load_map(frag)
        line = spans[0]["start_line"] if spans else 1
    # synctex records inputs by the name tex saw them; try the likely spellings
    relative = frag.resolve().relative_to(root.parent).as_posix()
    for name in (f"./{relative}", relative, frag.as_posix()):
        ok, out = _run([binary, "view", "-i", f"{int(line)}:0:{name}",
                        "-o", pdf.name], pdf.parent, _SYNCTEX_TIMEOUT)
        page, x, y = 0, 0.0, 0.0
        for ln in out.splitlines():
            s = ln.strip()
            if s.startswith("Page:") and not page:
                try:
                    page = int(s[5:].strip())
                except ValueError:
                    pass
            elif s.startswith("x:") and not x:
                try:
                    x = float(s[2:].strip())
                except ValueError:
                    pass
            elif s.startswith("y:") and not y:
                try:
                    y = float(s[2:].strip())
                except ValueError:
                    pass
        if page:
            return {"page": page, "x": x, "y": y, "section": section, "line": line}
    return {"error": f"synctex could not place {section or frag.name}:{line}"}


def _follow_fresh(pdf: Path, tex: Path, *, _scope: dict | None = None) -> tuple[bool, str]:
    """Follow only a selected compile whose consumed inputs and exact outputs
    remain verified by the existing build owner, including its SyncTeX map.
    Timestamp lockstep alone does not establish this source-to-map binding.
    Returns (fresh, reason); never compiles or repairs a receipt."""
    root = _repo_root().resolve()
    if not tex.resolve().is_relative_to(root) or pdf.resolve() != tex.resolve().with_suffix('.pdf'):
        return False, 'follow files do not identify the selected compile root'
    status = recompile_status(tex.relative_to(root).as_posix(), repo_root=root, _scope=_scope)
    if not status.get('fresh'):
        return False, status.get('reason') or 'compiled inputs and outputs are unverified; recompile'
    files = (status.get('outputs') or {}).get('files') or {}
    maps = [candidate for candidate in (pdf.with_suffix('.synctex.gz'), pdf.with_suffix('.synctex'))
            if candidate.is_file()]
    if not maps or not any(isinstance(files.get(candidate.relative_to(root).as_posix()), str)
                           for candidate in maps):
        return False, 'the exact SyncTeX map has no verified producer binding; recompile'
    return True, ''


def _mtime_of(p: Path) -> float | None:
    try:
        return p.stat().st_mtime
    except OSError:
        return None


def follow_status(file_param: str, *, corpus: str = '', compile_root: str = '') -> dict[str, Any]:
    """The ``.hy-stale`` read for W4.2 synctex-follow: is the continuous CM<->PDF
    follow AVAILABLE and FRESH? A uniform ``{id,label,present,fresh,reason,producer,
    fix,degraded}`` row the shared atom renders. Follow is DISABLED (degraded, the
    atom names why + how to fix) whenever the synctex BINARY is absent (the LOCAL-
    TEX-path law), no compiled pdf/synctex exists yet, or the synctex is stale
    against its verified inputs/outputs. PURE READ: it checks the existing build
    receipt and selected files; it NEVER compiles. ``fix`` only NAMES the gesture
    (compile / set env)."""
    label = "synctex-follow"
    producer = "latexmk -synctex=1 (the compile), resolved by the synctex binary"
    def row(present: bool, fresh: bool, reason: str, fix: str,
            **extra: Any) -> dict[str, Any]:
        present = bool(present)
        fresh = bool(present and fresh)
        return {"id": "synctex_follow", "label": label, "scope": "projection",
                "present": present, "fresh": fresh,
                "reason": (None if fresh else reason),
                "producer": producer, "built_ts": None, "fix": fix,
                "degraded": (not present) or (not fresh), **extra}
    p = _safe_path(file_param)
    if p is None:
        return row(False, False, "file must resolve inside the repo root",
                   "open the viewer with a ?file= inside the repo")
    if _synctex_bin() is None:                       # the LOCAL-TEX-PATH LAW: honest absent
        return row(False, False,
                   "the synctex binary is not on PATH and $LAPLACE_SYNCTEX_BIN is unset",
                   "set LAPLACE_SYNCTEX_BIN to your TeX distribution's synctex, or install synctex",
                   absent_binary=True)
    try:
        scope = _compile_scope(p, corpus=corpus, compile_root=compile_root)
    except CompileRootRefused as refused:
        recovery = refused.response()
        return row(False, False, str(refused), recovery['recovery'], reason_code=refused.reason,
                   next_read=recovery.get('next_read'), source_selection=recovery.get('source_selection'))
    tex = scope['root']
    pdf = tex.with_suffix(".pdf")
    if not pdf.is_file():
        return row(False, False, "no compiled pdf yet - follow needs a compiled artefact",
                   "compile the paper (▶) to mint the pdf + synctex")
    fresh, reason = _follow_fresh(pdf, tex, _scope=scope)
    return row(True, fresh, reason, "recompile the paper (▶) to refresh the synctex map")


# ---------------------------------------------------------------------------
# W4.4 — the debounced background recompile (single-latexmk mutex per manuscript)
# ---------------------------------------------------------------------------
# An explicit recompile GESTURE (POST /projection/recompile {corpus, by}) queues a
# latexmk run in the BACKGROUND: the request thread returns at once and the UI polls
# the PURE status read (GET /projection/recompile) for progress, re-anchoring the
# panes on completion (new pdf + synctex ⇒ the W4.2 follow re-enables). DEBOUNCED —
# a second request while one runs COALESCES: the cross-process filelock (the repo's
# own *.lock/filelock idiom, locking.canon_lock) is the single-latexmk MUTEX per
# manuscript, so a double-POST spawns exactly one latexmk. latexmk resolves per the
# LOCAL-TEX-PATH LAW; absent ⇒ honest refusal naming the env var, no thread. A failed
# compile surfaces its log tail through the .hy-stale idiom, state recoverable. The
# GET status NEVER compiles (the W1.2 purity law: a GET is always pure).

_RECOMPILE_FIX = ("set LAPLACE_LATEXMK_BIN to your TeX distribution's latexmk, "
                  "or install latexmk")
_RECOMPILE_PRODUCER = "latexmk -pdf -synctex=1 (the background recompile)"


def _manuscript_key(root_tex: Path) -> str:
    """A stable per-manuscript key for the mutex/status sidecars (the resolved
    compile-root path, hashed) — so two manuscripts never share a lock."""
    import hashlib
    try:
        s = str(root_tex.resolve())
    except OSError:
        s = str(root_tex)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def _recompile_lock_path(root_tex: Path) -> Path:
    """The per-manuscript recompile mutex, under the STATE dir (never in the repo,
    never a tracked/synced artefact) — the same placement law as locking.lock_path."""
    from laplace.engine import telemetry
    return telemetry.state_dir() / f"recompile-{_manuscript_key(root_tex)}.lock"


def _recompile_status_path(root_tex: Path) -> Path:
    """The per-manuscript recompile status sidecar the poll reads (state dir)."""
    from laplace.engine import telemetry
    return telemetry.state_dir() / f"recompile-{_manuscript_key(root_tex)}.status.json"


def _write_recompile_status(root_tex: Path, obj: dict[str, Any]) -> None:
    """Persist the recompile status atomically (write-temp-then-replace), so a poll
    can never read a half-written file while the worker transitions state."""
    path = _recompile_status_path(root_tex)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _read_recompile_status(root_tex: Path) -> dict[str, Any]:
    try:
        return json.loads(_recompile_status_path(root_tex).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _recompile_running(root_tex: Path) -> bool:
    """Is a recompile GENUINELY in flight? Probe the mutex non-blocking: if the OS
    lock can be claimed, no worker holds it (a stale ``running`` sidecar means the
    worker died). A distinct FileLock object contends with the worker's at the OS
    level even in-process, so this is a true liveness read. Pure — no compile."""
    from filelock import FileLock, Timeout
    lock = FileLock(str(_recompile_lock_path(root_tex)), timeout=0, thread_local=False)
    try:
        lock.acquire()
    except Timeout:
        return True                 # a worker holds the mutex → genuinely running
    else:
        lock.release()
        return False


def _build_output_paths(root_tex: Path, repo_root: Path) -> list[Path]:
    """Selected build evidence, never a repository scan.

    Missing root outputs are retained as markers. Nested aux inputs use TeX's
    root compile directory, just as the bibliography reader does; recorder
    outputs also cover nested bibliography/auxiliary artifacts.
    """
    root_tex, repo_root = root_tex.resolve(), repo_root.resolve()
    paths = {root_tex.with_suffix(ext) for ext in
             (".pdf", ".aux", ".bbl", ".synctex.gz", ".synctex", ".fls", ".bcf", ".run.xml")}
    pending, seen = [root_tex.with_suffix(".aux")], set()
    while pending:
        aux = pending.pop().resolve()
        if aux in seen or aux.suffix != ".aux" or not aux.is_relative_to(root_tex.parent):
            continue
        seen.add(aux)
        paths.add(aux)
        if aux.is_file():
            text = aux.read_text(encoding="utf-8", errors="replace")
            pending.extend(root_tex.parent / name for name in re.findall(r"\\@input\{([^}]+)\}", text))
    recorder = root_tex.with_suffix(".fls")
    if recorder.is_file():
        for line in recorder.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.startswith(("OUTPUT ", "INPUT ")):
                continue
            path = (root_tex.parent / line.split(" ", 1)[1].strip().strip('"')).resolve()
            if path.suffix.lower() in {".aux", ".bbl", ".bcf"} or path.name.endswith(".run.xml"):
                paths.add(path)
    return sorted({path.resolve() for path in paths if path.resolve().is_relative_to(repo_root)})


def _output_sha256(path: Path) -> str | None:
    """Stream selected artifact bytes; memory does not scale with PDF size."""
    try:
        with path.open("rb") as stream:
            import os
            before = os.fstat(stream.fileno())
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
            after = os.fstat(stream.fileno())
            current = path.stat()
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, field) != getattr(after, field) or
               getattr(after, field) != getattr(current, field) for field in fields):
            raise OSError("build output changed while reading: " + str(path))
        return digest.hexdigest()
    except FileNotFoundError:
        return None


def _build_generated_auxiliaries(root_tex: Path, repo_root: Path, *, generated_bib: bool = False) -> list[str]:
    """Producer-declared generated artifacts, retained for explicit repair only."""
    paths = set()
    recorder = root_tex.with_suffix(".fls")
    if recorder.is_file():
        for line in recorder.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("OUTPUT "):
                paths.add((root_tex.parent / line[7:].strip().strip('"')).resolve())
    # Latexmk's rule database distinguishes generated .bbl from a supplied .bbl
    # input. Parse only its generated blocks, never arbitrary input paths.
    database = root_tex.with_suffix(".fdb_latexmk")
    if database.is_file():
        generated = successful_rule = False
        for line in database.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("["):
                header = re.fullmatch(r'\["[^"\n]+"\]\s+([0-9.]+)\s+.*\s+([+-]?\d+)\s*', line)
                successful_rule = bool(header and float(header.group(1)) > 0 and header.group(2) == "0")
                generated = False
            elif line.strip() == "(generated)":
                generated = successful_rule
            elif line.lstrip().startswith(("[", "(")):
                generated = False
            elif generated:
                match = re.fullmatch(r'\s*"([^"\n]+)"\s*', line)
                if match:
                    paths.add((root_tex.parent / match.group(1)).resolve())
    if generated_bib:
        aux = root_tex.with_suffix(".aux")
        if aux.is_file() and "\\bibdata" in aux.read_text(encoding="utf-8", errors="replace"):
            paths.add(root_tex.with_suffix(".bbl"))
    return sorted(path.relative_to(repo_root).as_posix() for path in paths
                  if path.is_relative_to(repo_root) and
                  (path.suffix in {".aux", ".bbl", ".bcf"} or path.name.endswith(".run.xml")))


def _build_output_snapshot(root_tex: Path, repo_root: Path, *, generated_bib: bool = False,
                           producer: bool = True) -> dict[str, Any]:
    return {"version": 1, "root": root_tex.resolve().relative_to(repo_root.resolve()).as_posix(),
            "files": {path.relative_to(repo_root.resolve()).as_posix(): _output_sha256(path)
                      for path in _build_output_paths(root_tex, repo_root)},
            "generated": _build_generated_auxiliaries(root_tex, repo_root, generated_bib=generated_bib) if producer else []}


def _build_output_currentness(root_tex: Path, repo_root: Path, receipt: Any) -> dict[str, Any]:
    if (not isinstance(receipt, dict) or receipt.get("version") != 1 or
            receipt.get("root") != root_tex.resolve().relative_to(repo_root.resolve()).as_posix() or
            not isinstance(receipt.get("files"), dict)):
        return {"state": "LEGACY_UNVERIFIED", "current": False, "changes": [],
                "reason": "the compiled outputs have no supported producer receipt; rebuild to verify them"}
    try:
        actual = _build_output_snapshot(root_tex, repo_root, producer=False)
    except OSError as exc:
        return {"state": "UNAVAILABLE", "current": False, "changes": [], "reason": str(exc)}
    expected, observed = receipt["files"], actual["files"]
    changes = sorted(path for path in set(expected) | set(observed)
                     if path not in expected or path not in observed or expected[path] != observed[path])
    return {"state": "CHANGED" if changes else "VERIFIED", "current": not changes,
            "changes": changes, "reason": ("compiled outputs changed: " + ", ".join(changes)) if changes else None}


def _recompile_worker(root_tex: Path, file_param: str, corpus: str, by: str,
                      lock: Any, repo_root: Path | None = None,
                      prior_status: dict[str, Any] | None = None, compile_root: str = '',
                      build_target: dict | None = None, build_job: dict | None = None) -> None:
    """Run the queued compile, holding the mutex for its whole duration, and record
    the terminal transition to the status sidecar the poll reads. The lock is
    released on EVERY path (a crashed compile can never wedge the manuscript)."""
    from laplace.manuscript import build_jobs
    import contextlib
    prior = prior_status or {}
    retained_pdf = None
    try:
        retained_pdf = build_jobs.preserve_pdf(root_tex,prior,(repo_root or _repo_root()).resolve()) if build_job else None
        from laplace.manuscript import tex_dependencies
        active_root = (repo_root or _repo_root()).resolve()
        scope = _compile_scope(_safe_path(file_param, active_root), corpus=corpus,
                               compile_root=compile_root, repo_root=active_root,build_target=build_target)
        before = tex_dependencies.snapshot(root_tex, active_root)
        compile_started_ns = time.time_ns()
        prior = _read_recompile_status(root_tex) if prior_status is None else prior_status
        with build_jobs.bind(root_tex,build_job,active_root) if build_job else contextlib.nullcontext():
            res = compile_tex(file_param, repo_root=active_root, _prior_status=prior, _scope=scope)
        compile_finished_ns = time.time_ns()
        dependencies = tex_dependencies.snapshot(root_tex, active_root)
        changed_during = sorted(set(tex_dependencies.changed(before, active_root)) |
                                set(tex_dependencies.modified_since(
                                    dependencies, active_root, compile_started_ns,
                                    compile_finished_ns)))
        if res.get("ok") and changed_during:
            res = {**res, "ok": False,
                   "log_tail": (res.get("log_tail", "") + "\nConsumed inputs changed during compile: "
                                + ", ".join(changed_during)).strip()}
        derived = {}
        if build_target is not None:
            from laplace.manuscript import build_targets
            try:
                build_targets.resolve(build_target,corpus,active_root)
            except build_targets.TargetRefused:
                res = {**res,'ok':False,'log_tail':res.get('log_tail','')+'\nIssued derived target basis changed during compile.'}
            retained = ({'build_target':build_target,'outputs':res.get('outputs'),
                         'dependencies':dependencies,'finished':time.time()} if res.get('ok') else build_targets.retained(prior))
            derived = {'build_target':build_target,**({'last_successful_derived':retained} if build_target['kind']!='candidate' else {})}
        successful = ({'outputs':res.get('outputs'),'dependencies':dependencies,
                       'pdf':res.get('pdf'),'build_job':build_job,'finished':time.time()} if res.get('ok') else
                      build_jobs.previous_success(prior))
        terminal = {
            "state": "done" if res.get("ok") else "error",
            "ok": bool(res.get("ok")), "log_tail": res.get("log_tail", ""),
            "pdf": res.get("pdf"), "file": file_param, "corpus": corpus,
            "by": by, "dependencies": dependencies,
            "outputs": res.get("outputs") if res.get("ok") else None,
            "generated_outputs": ((res.get("outputs") or {}).get("generated") or
                                  (prior.get("outputs") or {}).get("generated") or
                                  prior.get("generated_outputs") or []),
            "changed_during_compile": changed_during, "finished": time.time(),
            'last_successful_build':successful,**derived}
        if build_job:build_jobs.finish(root_tex,build_job,terminal,retained_pdf,repo_root=active_root)
        else:_write_recompile_status(root_tex,terminal)
    except Exception as exc:                    # a background thread must never die silently
        derived = {}
        if build_target is not None:
            from laplace.manuscript import build_targets
            derived = {'build_target':build_target,**({'last_successful_derived':build_targets.retained(prior_status)} if build_target['kind']!='candidate' else {})}
        terminal = {
            "state": "cancelled" if isinstance(exc,build_jobs.BuildCancelled) else "error", "ok": False,
            "log_tail": f"recompile crashed: {exc!r}", "pdf": None,
            "file": file_param, "corpus": corpus, "by": by, "finished": time.time(),
            'last_successful_build':build_jobs.previous_success(prior),**derived}
        if build_job:build_jobs.finish(root_tex,build_job,terminal,retained_pdf,repo_root=(repo_root or _repo_root()).resolve())
        else:_write_recompile_status(root_tex,terminal)
    finally:
        try:
            lock.release()
        except Exception:
            pass


def recompile(file_param: str, corpus: str, by: str, *, repo_root: Path | None = None,
              compile_root: str = '', _selection: dict | None = None,
              build_target: dict | None = None) -> tuple[int, dict[str, Any]]:
    """POST /projection/recompile — queue a DEBOUNCED background latexmk run. Returns
    ``(http_status, row)``. The cross-process filelock is the single-latexmk mutex per
    manuscript: a second request while one runs COALESCES (200, ``running``,
    ``coalesced:true``) and spawns NOTHING. latexmk resolves per the local-TeX-path
    LAW; absent ⇒ stated refusal (400, present:false, fix names the env var, no
    thread). NEVER reached on a GET (the W1.2 purity law is enforced in ``handle``)."""
    p = _safe_path(file_param, repo_root)
    if p is None:
        return 403, {"status": "refused", "present": False, "degraded": True,
                     "reason": "file must resolve inside the repo root",
                     "fix": "open the viewer with a ?file= inside the repo"}
    if build_target is not None and build_target.get('kind')=='candidate':
        from laplace.manuscript import build_targets
        build_targets.ensure_candidate_stage(build_target,corpus,(repo_root or _repo_root()).resolve())
    if not p.is_file():
        return 404, {"status": "refused", "present": False, "degraded": True,
                     "reason": f"no such file: {p.name}",
                     "fix": "open a real tex file, then recompile"}
    scope = _compile_scope(p, corpus=corpus, compile_root=compile_root, repo_root=repo_root,
                           _selection=_selection,build_target=build_target)
    root = scope['root']
    from laplace.manuscript import build_jobs
    active_root = (repo_root or _repo_root()).resolve()
    proposed_job = build_jobs.issue(scope,active_root)
    if _latexmk_bin() is None:                  # LOCAL-TEX-PATH LAW: honest absent, no thread
        return 400, {"status": "absent", "present": False, "fresh": False,
                     "degraded": True, "absent_binary": True,
                     "reason": "latexmk is not on PATH and $LAPLACE_LATEXMK_BIN is unset",
                     "fix": _RECOMPILE_FIX}
    from filelock import FileLock, Timeout
    lock = FileLock(str(_recompile_lock_path(root)), timeout=0, thread_local=False)
    try:
        lock.acquire()                          # non-blocking CLAIM: the debounce gate
    except Timeout:
        prior = _read_recompile_status(root)
        job = prior.get('build_job')
        if build_target is not None and build_target.get('kind')=='candidate' and prior.get('state') not in build_jobs.ACTIVE:
            return 409, {'status':'refused','reason':'The candidate cache owner is busy; no compiler was started. Retry the issued build action.'}
        if build_target is not None and build_target.get('kind')=='publication-edition' and prior.get('state') not in build_jobs.ACTIVE:
            return 409, {'status':'refused','reason':'This edition is being prepared; no compiler was started. Read the editions and build the newly issued target.'}
        if prior.get('state')=='cancelling' or job and not build_jobs.same_basis(job,proposed_job):
            return 409, {'status':'refused','reason':'The existing build is stopping or has another input basis; no new build was launched.',
                **(build_jobs.handles(job,prior) if job else {})}
        derived = {}
        if build_target is not None:
            from laplace.manuscript import build_targets
            derived = {'build_target':build_target,'status_read':build_targets.handles(corpus,build_target)['status_read']}
        return 200, {"status": "running", "coalesced": True,
                     "reason": "a recompile is already running for this manuscript "
                               "(coalesced) — poll the status", "file": file_param,
                     "corpus": corpus,**derived,**(build_jobs.handles(job,prior) if job else {})}
    # we hold the mutex; record RUNNING before spawning so an immediate poll sees it,
    # then hand the held lock to the worker (thread_local=False ⇒ the worker thread
    # can release a lock this request thread acquired).
    prior = _read_recompile_status(root)
    if build_target is not None and build_target.get('kind')!='candidate':
        # The issued target was checked before this mutex was claimed; check it again now that this
        # request holds the per-root boundary that edition preparation also holds while it writes.
        from laplace.manuscript import build_targets
        try:
            build_targets.resolve(build_target,corpus,active_root)
        except build_targets.TargetRefused as error:
            lock.release()
            return 409, {'status':'refused','reason':str(error)+' No compiler was started.',**error.details}
    if build_jobs.processes_active(prior) or prior.get('cleanup_unproved') or prior.get('build_job') and prior.get('state') in build_jobs.ACTIVE:
        lock.release()
        return 409, {'status':'refused','reason':'The previous job requires owned-process recovery. Inspect/cancel its exact job before retrying.',
            **(build_jobs.handles(prior['build_job'],prior) if prior.get('build_job') else {})}
    derived = {}
    if build_target is not None:
        from laplace.manuscript import build_targets
        derived = {'build_target':build_target,**({'last_successful_derived':build_targets.retained(prior)} if build_target['kind']!='candidate' else {})}
    with build_jobs.control(root):
        _write_recompile_status(root, {"state": "running", "ok": None, "log_tail": "",
                                       "pdf": None, "file": file_param, "corpus": corpus,
                                       "by": by, "started": time.time(),
                                       'build_job':proposed_job,
                                       'last_successful_build':build_jobs.previous_success(prior),**derived})
        if _read_recompile_status(root).get('build_job')!=proposed_job:
            lock.release()
            return 409, {'status':'refused','reason':'The exact build owner could not be durably published; no compiler process was launched.'}
    threading.Thread(target=_recompile_worker,
                     args=(root, file_param, corpus, by, lock, repo_root, prior, scope['compile_root'],build_target,proposed_job), daemon=True, name="writing-pdf-build").start()
    return 200, {"status": "started", "coalesced": False, "file": file_param,
                 "corpus": corpus, "by": by,**build_jobs.handles(proposed_job),**({'build_target':build_target,
                    'status_read':build_targets.handles(corpus,build_target)['status_read']} if build_target is not None else {})}


def recompile_status(file_param: str, *, repo_root: Path | None = None, corpus: str = '',
                     compile_root: str = '', _scope: dict | None = None, _selection: dict | None = None,
                     build_target: dict | None = None) -> dict[str, Any]:
    """GET /projection/recompile — the ``.hy-stale`` poll row for W4.4: the live
    recompile state joined to the freshness the panes re-anchor on. PURE READ — it
    stats the status sidecar, the mutex, and the pdf/synctex; it NEVER compiles (the
    W1.2 GET-purity law). Shape = the uniform ``.hy-stale`` row + ``{state, running,
    ok, log_tail, pdf}``; ``fresh`` is True only when a compiled pdf is in synctex
    lockstep and no run is in flight (⇒ the W4.2 follow re-enables)."""
    def base(**extra: Any) -> dict[str, Any]:
        row = {"id": "recompile", "label": "recompile", "scope": "projection",
               "producer": _RECOMPILE_PRODUCER, "built_ts": None}
        if corpus:
            row.update(project=corpus,corpus=corpus)
        if build_target is not None:
            row.update(project=corpus,corpus=corpus,build_target=build_target)
        row.update(extra)
        return row
    p = _safe_path(file_param, repo_root)
    if p is None:
        return base(present=False, fresh=False, degraded=True, state="idle",
                    running=False, ok=None,
                    reason="file must resolve inside the repo root",
                    fix="open the viewer with a ?file= inside the repo")
    if build_target is not None and _scope is None:
        # Target admission precedes toolchain availability even on a pure poll;
        # an absent compiler must not disguise a changed issued scope.
        _scope = _compile_scope(p,corpus=corpus,compile_root=compile_root,repo_root=repo_root,
                                _selection=_selection,build_target=build_target)
    if _latexmk_bin() is None:                  # LOCAL-TEX-PATH LAW: honest absent
        from laplace.manuscript import build_jobs
        try:
            observed_scope = _scope or _compile_scope(p,corpus=corpus,compile_root=compile_root,
                repo_root=repo_root,_selection=_selection,build_target=build_target)
            observed_root=observed_scope['root']
            old=_read_recompile_status(observed_root)
            if old.get('build_job'):
                active=build_jobs.processes_active(old)
                running=old.get('state') in build_jobs.ACTIVE and (_recompile_running(observed_root) or active)
                return base(present=observed_root.with_suffix('.pdf').is_file(),fresh=False,degraded=True,
                    absent_binary=True,state=old.get('state','idle'),running=running,ok=old.get('ok'),
                    reason='latexmk is unavailable; an existing addressed job remains inspectable/cancellable.',
                    log_tail=old.get('log_tail',''),last_successful_build=old.get('last_successful_build'),
                    owned_processes_active=bool(build_jobs._members(old)),replacement_blocked=active or bool(old.get('cleanup_unproved')),
                    **build_jobs.handles(old['build_job'],old))
        except CompileRootRefused:
            pass
        return base(present=False, fresh=False, degraded=True, absent_binary=True,
                    state="idle", running=False, ok=None,
                    reason="latexmk is not on PATH and $LAPLACE_LATEXMK_BIN is unset",
                    fix=_RECOMPILE_FIX)
    try:
        scope = _scope or _compile_scope(p, corpus=corpus, compile_root=compile_root, repo_root=repo_root,
                                         _selection=_selection,build_target=build_target)
    except CompileRootRefused as refused:
        recovery = refused.response()
        return base(present=False, fresh=False, degraded=True, state='error', running=False, ok=False,
                    reason=str(refused), reason_code=refused.reason, fix=recovery['recovery'],
                    next_read=recovery.get('next_read'), source_selection=recovery.get('source_selection'))
    root = scope['root']
    st = _read_recompile_status(root)
    state = st.get("state", "idle")
    from laplace.manuscript import build_jobs
    running = (state in build_jobs.ACTIVE) and (_recompile_running(root) or build_jobs.processes_active(st))
    log_tail = st.get("log_tail", "")
    if state in build_jobs.ACTIVE and not running:  # no mutex or owned process remains
        state = "error"                          # → the worker died; honest + recoverable
        log_tail = log_tail or ("the recompile worker is no longer running (it may have "
                                "crashed) - recompile again")
    pdf = root.with_suffix(".pdf")
    have_pdf = pdf.is_file()
    syn_ok = have_pdf and _synctex_fresh(pdf)
    expected = st.get("dependencies") if isinstance(st.get("dependencies"), dict) else None
    if expected is None:
        dependency_changes = []
        dependency_reason = "the compiled pdf has no dependency receipt"
    else:
        from laplace.manuscript import tex_dependencies
        dependency_changes = tex_dependencies.changed(expected, (repo_root or _repo_root()).resolve())
        dependency_reason = (("compiled inputs changed: " + ", ".join(dependency_changes))
                             if dependency_changes else None)
    dependencies_ok = expected is not None and not dependency_changes
    output_proof = _build_output_currentness(root, (repo_root or _repo_root()).resolve(), st.get("outputs"))
    fresh = (syn_ok and dependencies_ok and output_proof["current"] and
             not running and state == "done" and st.get("ok") is True)
    target_current = build_target is None or st.get('build_target')==build_target
    if not target_current:
        fresh = False
        dependency_reason = 'The saved build consumed another derived plan/source-selection basis; rebuild this issued target.'
    if running:
        reason, fix = ("the build is stopping…", "wait until owned compiler cleanup is confirmed") if state=='cancelling' else ("a recompile is running…", "wait for the recompile to finish")
    elif state == 'cancelled':
        reason, fix = ('the build was cancelled; previous verified PDF retained when available',
                       'Inspect the retained output or deliberately start a new build.')
    elif state == "error":
        reason, fix = ("the last recompile failed - see the log tail",
                       "fix the LaTeX error and recompile (▶)")
    elif not have_pdf:
        reason, fix = ("no compiled pdf yet",
                       "recompile the paper (▶) to mint the pdf + synctex")
    elif not syn_ok:
        reason, fix = ("the pdf and its synctex are out of lockstep - recompile",
                       "recompile the paper (▶) to refresh the synctex map")
    elif not target_current:
        reason, fix = dependency_reason, 'Inspect/rebuild the current issued derived target.'
    elif not dependencies_ok:
        reason, fix = (dependency_reason,
                       "recompile the paper (▶) to refresh changed inputs")
    elif not output_proof["current"]:
        reason, fix = output_proof["reason"], "recompile the paper (▶) to verify its outputs"
    else:
        reason, fix = None, "recompile the paper (▶) to rebuild"
    return base(present=have_pdf, fresh=bool(fresh), degraded=(not fresh),
                state=state, running=running, ok=st.get("ok"),
                log_tail=log_tail, pdf=st.get("pdf"), by=st.get("by"),
                started=st.get("started"), finished=st.get("finished"),
                dependency_changes=dependency_changes, inputs_current=dependencies_ok and target_current,
                input_revisions=expected,
                outputs_current=output_proof["current"],
                output_proof=output_proof["state"], output_changes=output_proof["changes"],
                outputs=st.get("outputs"), last_successful_build=st.get('last_successful_build'),
                **{key:st[key] for key in ('preview_ref','build_receipt_id','preview_publication','preview_error','preview_diagnostics') if key in st},
                built_ts=_mtime_of(pdf), reason=reason, fix=fix,
                replacement_blocked=build_jobs.processes_active(st) or bool(st.get('cleanup_unproved')),
                **(build_jobs.handles(st['build_job'],st) if st.get('build_job') else {}),
                **({'build_target':build_target,'consumed_build_target':st.get('build_target'),
                    'target_basis_current':target_current} if build_target is not None else {}))


def forks(file_param: str, project: str) -> dict[str, Any]:
    """The paragraph-level DECISION LAYER for a fragment: every paragraph span
    joined to the pipeline's forks against it — the realiser's decisions
    (prose-provenance ``qualifications``), the weld's decisions, and the
    node-precise ``nodes_realised``. This is what the editor view overlays so the
    author's eyes land where the pipeline chose or hesitated (his ask, this
    session). Generic: the sidecars resolve through the registry
    (``load_provenance`` / ``load_decisions``); the project is supplied by the
    client, exactly like ``/node`` and ``/feedback``. Paragraphs with no fork are
    returned too (empty lists), so the caller sees the whole span layout."""
    p = _safe_path(file_param)
    if p is None:
        return {"error": "file must resolve inside the repo root"}
    if not p.is_file():
        return {"error": f"no such file: {p.name}"}
    if not project:
        return {"error": "corpus= (project) required"}
    from laplace.pipeline import document_model as dm
    paras = parse_paragraphs(p.read_text(encoding="utf-8", errors="replace"))
    provenance_by_section: dict[str, list[dict]] = {}
    dec_by_id: dict[str, list] = {}
    for sid in {pp["section"] for pp in paras if pp["section"]}:
        provenance_by_section[sid] = dm.load_provenance(project, sid) or []
        for rec in (dm.load_decisions(project, sid) or []):
            if rec.get("spec_id"):
                dec_by_id.setdefault(rec["spec_id"], []).append(rec)
    def _dedup(seq):
        return list(dict.fromkeys(seq))
    out = []
    occurrence_by_section: dict[str, int] = {}
    for pp in paras:
        section = pp.get("section") or ""
        occurrence = occurrence_by_section.get(section, 0)
        records = provenance_by_section.get(section, [])
        if occurrence >= len(records):
            return {"error": "paragraph marker/provenance occurrence mismatch",
                    "file": p.name, "project": project, "section": section,
                    "occurrence": occurrence}
        provenance = records[occurrence]
        marker_ids = pp.get("spec_ids") or ([pp["spec_id"]] if pp.get("spec_id") else [])
        record_ids = provenance.get("spec_ids") or (
            [provenance["spec_id"]] if provenance.get("spec_id") else [])
        if marker_ids != record_ids:
            return {"error": "paragraph marker/provenance spec_ids mismatch",
                    "file": p.name, "project": project, "section": section,
                    "occurrence": occurrence, "markers": marker_ids,
                    "provenance": record_ids}
        occurrence_by_section[section] = occurrence + 1
        decs: list = []
        for sid in marker_ids:
            decs += dec_by_id.get(sid, [])
        out.append({**pp,
                    "nodes_realised": _dedup(provenance.get("nodes_realised", []) or []),
                    "qualifications": list(provenance.get("qualifications", []) or []),
                    "citations": _dedup(provenance.get("citations", []) or []),
                    "decisions": decs})
    for section, records in provenance_by_section.items():
        consumed = occurrence_by_section.get(section, 0)
        if consumed != len(records):
            return {"error": "paragraph provenance has no physical marker occurrence",
                    "file": p.name, "project": project, "section": section,
                    "physical_occurrences": consumed, "provenance_records": len(records)}
    return {"file": p.name, "project": project, "paragraphs": out}


def _feedback_ledger(file_param: str, *, corpus: str = '', compile_root: str = '') -> Path | None:
    """The artefact's comment ledger: ``feedback/feedback.jsonl`` beside the
    compile root (same shape and mechanism as the paper_self_theory ledger)."""
    p = _safe_path(file_param)
    if p is None:
        return None
    scope = _compile_scope(p, corpus=corpus, compile_root=compile_root)
    if scope['source'] is not None:
        from laplace.manuscript import manuscript_source
        return manuscript_source.feedback_ledger(corpus, _repo_root(), source=scope['source'])
    return scope['root'].parent / "feedback" / "feedback.jsonl"


# ---------------------------------------------------------------------------
# the handler - the scanner dispatches /projection* here
# ---------------------------------------------------------------------------

def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key, default)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else default
    return (v or default).strip()


def _json(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")


# W4.3 retirements (the W0.3 410 idiom): the PNG raster serving path (/projection/pages,
# /projection/page) and the poppler text-layer serving path (/projection/textlayer) are
# GONE from the viewer. The viewer renders the pdf client-side with pdf.js and builds its
# selectable text layer from pdf.js getTextContent - no pdftoppm, no poppler, on any
# serving route. The pdf itself streams from /projection/pdf; its metadata from
# /projection/pdfinfo. (render_pages / text_layer survive as importable OFFLINE tooling
# for the frozen export scripts + the lock reader - never reachable from handle().)
_RETIRED_PNG = {"error": "gone", "retired": "W4.3",
                "reason": "the PNG raster path is retired; the viewer renders the pdf "
                          "in-browser with pdf.js",
                "use": "/projection/pdf (bytes) + /projection/pdfinfo (metadata)"}
_RETIRED_TEXTLAYER = {"error": "gone", "retired": "W4.3",
                      "reason": "the poppler text layer is retired; the viewer builds "
                                "the selectable text layer from pdf.js getTextContent",
                      "use": "pdf.js native text layer (client-side)"}


def _source_maintenance_warning(out: dict, operation: str, exc: Exception) -> None:
    """An optional follow-through cannot erase an already settled source effect."""
    out.setdefault("maintenance_warnings", []).append({"operation": operation,
        "reason": str(exc)[:400], "recovery": "/shared/versions"})


def _save_source(p: Path, query: dict, body: bytes, *, source_changes=None):
    """Caller has admitted the exact inspected basis under its physical lease."""
    text = body.decode("utf-8", errors="replace")
    intended = text.encode("utf-8")
    before = p.read_bytes()
    from laplace.manuscript import source_effects
    def effect():
        return source_effects.receipt(_q1(query, "corpus"), _q1(query, "expected_selection") or None,
            [source_effects.observed_file(_repo_root(), p, before, intended)])
    if before == intended:
        # Ordinary Save is not an archival or scientific occurrence. The
        # inspected guard was checked under the lease before reaching here.
        # No inode/mtime, snapshot, index, exemplar or ledger changes follow.
        no_op_effect = effect()
        return _json(200, {"ok":True, **source_effects.raw_compatibility(no_op_effect),
            "file":_rel_to_root(p), "bytes":len(intended), "lines":text.count("\n")+1,
            "consumed_source_digest":_q1(query,"expected_source_digest"),
            "expected_source_digest":"sha256:"+hashlib.sha256(intended).hexdigest(),
            "banked":False, "exemplar":{"banked":False,"reason":"source bytes unchanged"}, "source_effect":no_op_effect})
    # newline="" so the payload round-trips byte-exact (no \n -> \r\n on Windows)
    _replace_source(p, intended)
    if source_changes is not None:
        source_changes.append((p, before, intended))
    out: dict[str, Any] = {"ok": True, "source_committed": True, "changed":True, "file": _rel_to_root(p), "bytes": len(body),
                           "lines": text.count("\n") + 1,
                           "consumed_source_digest": _q1(query, "expected_source_digest"),
                           "expected_source_digest": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()}
    out["source_effect"] = effect()
    out.update(source_effects.raw_compatibility(out["source_effect"]))
    # W8 (J4): banking is OPT-IN — only a save carrying ?bank= mints an editor-save
    # VERSION, so other tex writers never bank spuriously. The editor pane opts in
    # (bank=editor); the corpus rides via store.fetchJSON's default inject. The
    # banked bytes are the file's on-disk bytes (text re-encoded, newline-exact).
    bank = _q1(query, "bank")
    if bank:
        corpus = _q1(query, "corpus")
        try:
            md = _manuscript_dir_for(corpus)
            if md is not None:
                man = bank_editor_save(md, p, text.encode("utf-8"),
                                       author=_q1(query, "author") or bank,
                                       surface=_q1(query, "surface") or "editor")
                out["version_id"] = man["version_id"]
            else:
                out["banked"] = False
                out["bank_note"] = "no manuscript store for the corpus — save not banked"
        except Exception as exc:
            out["snapshot_status"] = "UNPROVED"
            _source_maintenance_warning(out, "bank_editor_save", exc)
        # THE EXEMPLAR DOOR (bank=editor): the save also banks ONE exemplar row
        # carrying the server-derived hunks against the newest machine-minted
        # baseline, and the response carries the receipt so the front end can
        # echo it in the same frame (row id + destination + counts). It is the
        # one commit made without a deposit gesture, so it announces itself.
        # THE ACTOR LAW: the exemplar inherits the save's explicit ``author``
        # param and refuses without it — ``bank=`` is a mode, not an actor.
        if bank == "editor":
            try:
                from laplace.manuscript import review_surface as _rv
                out["exemplar"] = _rv.bank_exemplar(
                    corpus, _rel_to_root(p), author=_q1(query, "author"),
                    surface=_q1(query, "surface") or "editor", before=before, after=intended)
            except Exception as exc:
                _source_maintenance_warning(out, "bank_exemplar", exc)
    return _json(200, out)



def handle(path: str, query: dict, method: str, body: bytes) -> tuple[int, str, bytes] | None:
    try:
        return _handle(path, query, method, body)
    except CompileRootRefused as refused:
        return _json(409, refused.response())
    except ValueError as error:
        from laplace.manuscript.build_targets import TargetRefused
        if isinstance(error,TargetRefused):
            return _json(409,{'error':str(error),**error.details})
        raise


def _handle(path: str, query: dict, method: str, body: bytes) -> tuple[int, str, bytes] | None:
    """Route one /projection* request. Returns (status, content_type, body) or None
    when the path is not ours (the scanner falls through to its own routing)."""
    if path != "/projection" and not path.startswith("/projection/"):
        return None
    method = (method or "GET").upper()

    if path == "/projection" and method == "GET":
        # W2 CONSOLIDATION: the projection READER folded into /artefact's read mode (the
        # scanner 301-redirects the bare /projection route). This module keeps its
        # /projection/* DATA producers (re-housed by the artefact panes); the PAGE is gone —
        # so it names where it went instead of serving the deleted projection_viewer.html.
        return _json(200, {"consolidated_into": "/artefact",
                           "note": "the projection reader is the read mode of the artefact surface (W2)"})

    if path == "/projection/context" and method == "GET":
        # the bare-route bootstrap (W0.2): the active project + its server-derived
        # main tex (repo-relative), so a bare /projection opens on the real corpus
        # instead of the "no ?file= given" shell. Newest-PDF fallback is honestly
        # labelled by project_context; never a fabricated tex path.
        from laplace.research import corpus_ingest as _ci
        return _json(200, _ci.project_context(_repo_root(), _q1(query, "corpus")))

    if path == "/projection/tex":
        p = _safe_path(_q1(query, "file"))
        if p is None:
            return _json(403, {"error": "file must resolve inside the repo root"})
        from laplace.manuscript import manuscript_source
        from contextlib import nullcontext
        corpus = _q1(query, "corpus")
        if method == "GET":
            if not p.is_file():
                return _json(404, {"error": f"no such file: {p.name}"})
            try:
                access = manuscript_source.source_access(corpus, p, _repo_root()) if corpus else None
                if corpus and _q1(query,'view')=='source':source_query=manuscript_source.validate_source_query(query)
            except manuscript_source.SourceAccessError as exc:
                failure = dict(exc.response)
                return _json(failure.pop('status'), failure)
            except ValueError as exc:
                return _json(422, {'error':str(exc),'reason':'source-query-invalid'})
            if _q1(query, "view") == "source":
                observed = _source_observation(p,query=source_query if corpus else None,access=access)
                if access:
                    observed.update(access)
                    observed.update(manuscript_source.source_handles(corpus, observed['file'], observed['expected_source_digest'], access))
                return _json(200, observed)
            return 200, "text/plain; charset=utf-8", p.read_bytes()
        if method == "POST":
            try:
                if not corpus:
                    # Unscoped legacy editing cannot bypass a registered document's
                    # selected-edition or read-only authority. No history is loaded.
                    manuscript_source.require_unregistered_source(p, _repo_root())
                changes = []
                with (manuscript_source.selection_mutation(corpus, _repo_root()) if corpus else nullcontext()):
                    with manuscript_source.source_mutation([p]):
                        access = manuscript_source.source_access(corpus, p, _repo_root(), writable=True, expected_selection=_q1(query, 'expected_selection')) if corpus else None
                        if corpus and not _q1(query, 'author').strip():
                            return _json(422, {'error':'An explicit author is required for a source save.','reason':'source-actor-required'})
                        if corpus:
                            try:manuscript_source.validate_source_query(query,write=True)
                            except ValueError as exc:return _json(422,{'error':str(exc),'reason':'source-query-invalid'})
                        conflict = _source_guard(p, _q1(query, "expected_source_digest"))
                        if conflict:
                            if corpus:
                                conflict['recovery']['query']['corpus'] = corpus
                            return _json(conflict.pop("status"), conflict)
                        code, mime, raw = _save_source(p, query, body, source_changes=changes)
                result = json.loads(raw)
                from laplace.manuscript import source_effects
                source_effects.finish(result, corpus, _repo_root(), result['source_effect'], changes=changes)
                if access:
                    result.update(selection_identity=access['selection_identity'],
                        invalidated=['manuscript','document','template-preview'] if result.get('changed') else [],
                        history_read={'method':'GET','route':'/authoring/history','query':{'project':corpus,'file':_rel_to_root(p)}})
                return _json(code, result)
            except manuscript_source.SourceAccessError as exc:
                failure = dict(exc.response)
                return _json(failure.pop('status'), failure)
            except manuscript_source.SourceLeaseError as exc:
                return _json(409, {"error": str(exc), "reason": "source-lease-unavailable"})

    if path == "/projection/restore" and method == "POST":
        # W8 (J4): restore a banked editor-save into the live file THROUGH the save path —
        # a restore is a NEW save (a new rail row), never a rewind. {file, version_id,
        # corpus} ride the query OR the JSON body.
        payload: dict[str, Any] = {}
        if body:
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        out = restore_editor_save(
            _q1(query, "corpus") or str(payload.get("corpus", "") or ""),
            _q1(query, "file") or str(payload.get("file", "") or ""),
            _q1(query, "version_id") or str(payload.get("version_id", "") or ""),
            _q1(query, "expected_source_digest") or payload.get("expected_source_digest"),
            _q1(query, "expected_selection") or payload.get("expected_selection"))
        return _json(out.pop("status", 200 if out.get("ok") else 400), out)

    if path == "/projection/compile" and method == "POST":
        # W8 (J4): the compile RECORDS which banked editor-save it built (stamp_compile
        # names the latest save's version_id in the response + a compile.json sidecar).
        return _json(200, stamp_compile(compile_tex(_q1(query, "file"), corpus=_q1(query, "corpus"), compile_root=_q1(query, "compile_root")), _q1(query, "corpus")))

    if path == "/projection/recompile":
        # W4.4: POST queues a DEBOUNCED background latexmk run (single-latexmk mutex,
        # coalescing); GET is the PURE status poll (the W1.2 law — a GET NEVER
        # compiles). {corpus, by} ride the JSON body OR the query.
        payload: dict[str, Any] = {}
        if body:
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        file_param = _q1(query, "file") or str(payload.get("file", "") or "")
        from laplace.manuscript.build_targets import decode
        build_target = decode(_q1(query,'build_target') or payload.get('build_target'),
                              project=_q1(query,'corpus') or str(payload.get('corpus') or ''))
        if method == "POST":
            corpus = _q1(query, "corpus") or str(payload.get("corpus", "") or "")
            by = _q1(query, "by") or str(payload.get("by", "") or "")
            status, row = recompile(file_param, corpus, by, compile_root=_q1(query, "compile_root") or str(payload.get("compile_root") or ""),build_target=build_target)
            if status == 200 and build_target is None: # Current manuscript save identity is not a derived build receipt.
                stamp_compile(row, corpus)    # version it is building (the latest banked save)
            return _json(status, row)
        if method == "GET":
            return _json(200, recompile_status(file_param, corpus=_q1(query, "corpus"), compile_root=_q1(query, "compile_root"),build_target=build_target))
        return _json(405, {"error": f"{method} {path} not supported"})

    if path == "/projection/pdf" and method == "GET":
        spelled = _q1(query, 'file') or ''
        receipt_named = bool(_q1(query, 'export_receipt'))
        saved_shape = spelled.lower().endswith('.pdf') and Path(spelled).parent.name == 'exports'
        if receipt_named or (saved_shape and _q1(query, 'corpus')):
            # a SAVED export is its own exact artifact (document_style.exported_pdf): an explicit export_receipt, or the
            # earlier file+corpus saved URL, selects it; it is read through its receipt, never through the selected
            # current root's membership. An explicit receipt never falls back to a current or build PDF (repair2
            # RP-R5-R1): a missing project or a mixed compile_root/build_target selector refuses before any bytes.
            if not _q1(query, 'corpus'):
                return _json(409, {'error': 'A saved export is read with its project (corpus).', 'reason': 'export-project-missing'})
            if _q1(query, 'compile_root') or _q1(query, 'build_target'):
                return _json(409, {'error': 'A saved export cannot be combined with a current compile root or build target.',
                                   'reason': 'export-selector-conflict'})
            from laplace.manuscript import document_style
            try:
                data, _receipt = document_style.exported_pdf(_q1(query, 'corpus'), spelled, _repo_root(),
                                                             receipt=_q1(query, 'export_receipt') or None)
            except document_style.ExportReadRefused as refused:
                return _json(409, {'error': str(refused), 'reason': refused.reason})
            expected = _q1(query, 'expected_content_revision')
            if expected and expected != 'sha256:' + hashlib.sha256(data).hexdigest():
                return _json(409, {'error': 'This PDF changed after it was inspected; the requested bytes were not served.',
                                   'reason': 'output-revision-conflict'})
            return 200, 'application/pdf', data
        if _q1(query,'build_target'):
            from laplace.manuscript import build_targets
            target = build_targets.decode(_q1(query,'build_target'),project=_q1(query,'corpus'))
            data = build_targets.saved_pdf(target,_q1(query,'corpus'),_repo_root(),
                _q1(query,'expected_content_revision'),requested_file=_q1(query,'file'))
            return 200,'application/pdf',data
        p = _safe_path(_q1(query, "file"))
        if p is None:
            return _json(403, {"error": "file must resolve inside the repo root"})
        if p.suffix.lower() == ".tex":                # accept the tex path too
            p = resolve_root(p, corpus=_q1(query, "corpus"), compile_root=_q1(query, "compile_root")).with_suffix(".pdf")   # a fragment's pdf is the paper's
        elif _q1(query, 'corpus') or _q1(query, 'compile_root'):
            scope = _compile_scope(p, corpus=_q1(query, 'corpus'), compile_root=_q1(query, 'compile_root'))
            if p != scope['root'].with_suffix('.pdf'):
                raise CompileRootRefused('The requested PDF is not the selected root output.', 'compile-root-output-unproved', corpus=_q1(query, 'corpus'))
        if not p.is_file():
            return _json(404, {"error": f"no compiled pdf at {p.name} - compile first"})
        data = p.read_bytes()
        expected = _q1(query, 'expected_content_revision')
        if expected and expected != 'sha256:' + hashlib.sha256(data).hexdigest():
            return _json(409, {'error':'This PDF changed after it was inspected. Read the document again; the requested bytes were not served.',
                'reason':'output-revision-conflict','recovery':{'method':'GET','route':'/authoring/document','query':{'project':_q1(query,'corpus')}}})
        return 200, "application/pdf", data

    if path == "/projection/doc" and method == "GET":
        model = doc_model(_q1(query, "file"), corpus=_q1(query, "corpus"), compile_root=_q1(query, "compile_root"))
        if "error" in model:
            status = 403 if "repo root" in model["error"] else 404
            return _json(status, model)
        return _json(200, model)

    if path == "/projection/map" and method == "GET":
        p = _safe_path(_q1(query, "file"))
        if p is None:
            return _json(403, {"error": "file must resolve inside the repo root"})
        if not p.is_file():
            return _json(404, {"error": f"no such file: {p.name}"})
        return _json(200, load_map(p))

    if path == "/projection/residue" and method == "GET":
        out = residue(_q1(query, "file"), _q1(query, "corpus"))
        if "error" in out:
            status = 403 if "repo root" in out["error"] else 404
            return _json(status, out)
        return _json(200, out)

    if path == "/projection/node" and method == "GET":
        nid = _q1(query, "id")
        corpus = _q1(query, "corpus")
        if not nid or not corpus:
            return _json(400, {"error": "id= and corpus= required"})
        brief = node_brief(corpus, nid)
        return _json(404 if "error" in brief else 200, brief)

    if path == "/projection/pages" and method == "GET":
        return _json(410, _RETIRED_PNG)             # W4.3: PNG serving path retired

    if path == "/projection/pdfinfo" and method == "GET":
        out = pdf_info(_q1(query, "file"), corpus=_q1(query, "corpus"), compile_root=_q1(query, "compile_root"))
        if "error" in out:
            return _json(403 if "repo root" in out["error"] else 404, out)
        return _json(200, out)

    if path == "/projection/page" and method == "GET":
        return _json(410, _RETIRED_PNG)             # W4.3: PNG serving path retired

    if path == "/projection/locate" and method == "GET":
        try:
            line = int(_q1(query, "line") or 0)
        except ValueError:
            line = 0
        out = synctex_locate(_q1(query, "file"), _q1(query, "section"), line, corpus=_q1(query, "corpus"), compile_root=_q1(query, "compile_root"))
        return _json(200 if "error" not in out else 422, out)

    if path == "/projection/follow" and method == "GET":
        # W4.2: the .hy-stale read for continuous CM<->PDF synctex-follow. PURE
        # READ (stats + binary probe, never a compile) — always 200; the row's
        # own present/fresh/degraded flags carry the honest verdict the atom renders.
        return _json(200, follow_status(_q1(query, "file"), corpus=_q1(query, "corpus"), compile_root=_q1(query, "compile_root")))

    if path == "/projection/synctex" and method == "GET":
        try:
            page = int(_q1(query, "page"))
            x = float(_q1(query, "x"))
            y = float(_q1(query, "y"))
        except ValueError:
            return _json(400, {"error": "page=, x=, y= numeric required"})
        out = synctex_anchor(_q1(query, "file"), page, x, y, corpus=_q1(query, "corpus"), compile_root=_q1(query, "compile_root"))
        return _json(200 if "error" not in out else 422, out)

    if path == "/projection/forks" and method == "GET":
        out = forks(_q1(query, "file"), _q1(query, "corpus"))
        return _json(200 if "error" not in out else 404, out)

    if path == "/projection/textlayer" and method == "GET":
        return _json(410, _RETIRED_TEXTLAYER)       # W4.3: text layer -> pdf.js native

    if path == "/projection/feedback":
        from laplace.manuscript import manuscript_bridge as mb
        ledger = _feedback_ledger(_q1(query, "file"), corpus=_q1(query, "corpus"), compile_root=_q1(query, "compile_root"))
        if ledger is None:
            return _json(403, {"error": "file must resolve inside the repo root"})
        rr = _repo_root()
        corpus = _q1(query, "corpus") or "projection"
        if method == "GET":
            return _json(200, mb.feedback_list(rr, corpus, ledger=ledger))
        if method == "POST":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                return _json(400, {"error": "bad json"})
            payload.setdefault("project", corpus)
            out = mb.feedback_add(rr, corpus, payload, ledger=ledger)
            return _json(200 if "error" not in out else 400, out)

    if path == "/projection/feedback/resolve" and method == "POST":
        from laplace.manuscript import manuscript_bridge as mb
        ledger = _feedback_ledger(_q1(query, "file"), corpus=_q1(query, "corpus"), compile_root=_q1(query, "compile_root"))
        if ledger is None:
            return _json(403, {"error": "file must resolve inside the repo root"})
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return _json(400, {"error": "bad json"})
        return _json(200, mb.feedback_resolve(
            _repo_root(), _q1(query, "corpus") or "projection",
            payload.get("id", ""), payload.get("status", "resolved"), ledger=ledger))

    return _json(405, {"error": f"{method} {path} not supported"})
