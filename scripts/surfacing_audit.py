"""Surfacing audit — prove nothing load-bearing is invisible to a fresh clone.

The fear this mechanises (Leg C bite C2, PLAN_2026-07-12): a fresh container clones
the repo and the pipeline silently lacks a file it *reads at run time*. The 2026-07-10
session found the C-hinge provenance pair (``projection_plan.base.json`` +
``.friction.jsonl``) and ``uv.lock`` hiding behind ``.gitignore`` rules; this script
turns that manual find into a mechanical, repeatable gate.

WHAT IT DOES
------------
1. Derives the pipeline's READ-SURFACE honestly, from two independent sources:
   * the **registry layout contract** (``pipeline/registry.py``): every path a
     :class:`Project` declares — ledgers, plans, manuscript/target dirs, glossaries,
     bibs, feedback ledgers, versions/evolutions dirs, and every ``stage_path`` under
     ``schema.STAGE_ARTIFACTS`` — resolved for every registered project (no hardcoded
     project names; the set comes from ``registry.all_projects()``).
   * a **static scan** of the pipeline organs (``src/laplace/pipeline/**``), the
     surfaces (``scanner.py``, ``review_surface.py``, ``storyboard.py``) and the
     workflow scripts (``.claude/workflows/*.{js,py}``) for repo-relative path
     literals (config files like ``profiles/pipeline/dials-v1.yaml``, runtime
     dotfiles like ``.nodemap.json``).

2. Classifies every surfaced path against git + the ~87 ``.gitignore`` rules:
   * ``tracked``          — in git; a fresh clone has it.
   * ``reconstructable``  — generated at run time; the repo itself documents the regen
                            command (a ``.gitignore`` comment flags it regenerable /
                            a cache / a build artifact), or it is a standard env/build
                            artifact. Absent-and-produced pipeline artifacts also land
                            here (a fresh clone rebuilds them exactly as this machine does).
   * ``violation``        — present on disk, IGNORED, read by the pipeline, and with NO
                            documented regen path. It exists only on this machine and
                            vanishes on clone. This is the C-hinge class.

   The sharp, evidence-based violation test is the intersection
   ``read-surface ∩ present-on-disk ∩ ignored ∩ ¬reconstructable``. An *absent* file is
   never a violation: a fresh clone missing it is identical to this machine missing it —
   the pipeline builds it (most registered projects are simply unbuilt).

3. Walks the ``.gitignore`` rules and reports, per rule, whether anything in the
   read-surface hides behind it (and whether any such hidden file is a violation).

EXIT CODE CONTRACT:  0 = no violations · 2 = violations listed.

Generic: repo root is an argument (default: this repo). Project set comes from the
registry. Tolerant of siblings mid-edit — a working-tree source that will not parse is
re-read from ``git show HEAD:<path>``.

    python scripts/surfacing_audit.py [REPO_ROOT] [--json OUT.json] [-q]
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True,
    )


def tracked_files(root: Path) -> set[str]:
    return set(_git(root, "ls-files").stdout.splitlines())


def ignored_present_files(root: Path) -> set[str]:
    """Files present on disk but ignored by git (would NOT survive a fresh clone)."""
    out = _git(root, "ls-files", "--others", "--ignored", "--exclude-standard").stdout
    return set(out.splitlines())


def head_source(root: Path, rel: str) -> str | None:
    """The committed text of a file (``git show HEAD:<rel>``) — the mid-edit fallback."""
    r = _git(root, "show", f"HEAD:{rel}")
    return r.stdout if r.returncode == 0 else None


_ATTR_RE = re.compile(r"^(.*):(\d+):(.*)$")


def attribute_rules(root: Path, paths: list[str]) -> dict[str, tuple[str, int, str]]:
    """Map each path -> (gitignore_source, line_no, pattern) via ``check-ignore -v``.

    Batched over stdin so the hot loop makes ONE subprocess call.
    """
    if not paths:
        return {}
    proc = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--verbose", "--stdin"],
        input="\n".join(paths), capture_output=True, text=True,
    )
    out: dict[str, tuple[str, int, str]] = {}
    for line in proc.stdout.splitlines():
        if "\t" not in line:
            continue
        head, path = line.split("\t", 1)
        m = _ATTR_RE.match(head)
        if not m:
            continue
        src, ln, pat = m.group(1), int(m.group(2)), m.group(3)
        out[path] = (src, ln, pat)
    return out


# ---------------------------------------------------------------------------
# .gitignore rule model + reconstructability
# ---------------------------------------------------------------------------

# Comment keywords that mark an ignored path as regenerable — the repo documenting
# its own regen path. If a rule's comment block carries one of these, the files it
# hides are RECONSTRUCTABLE, not violations.
_REGEN_KEYWORDS = (
    "regenerat", "regenerable", "regenerated", "rebuilt", "rebuild",
    "build artifact", "build products", "cache", "scratch", "runtime",
    "derived", "transient", "session-start", "reconstruction", "regrade",
    "local state", "local-only", "regen", "produced", "rendered", "renders",
    "compiled", "offline embedding", "re-laid", "re-embed",
)

# Standard env / build / tooling artifacts — reconstructable by definition, whatever
# the comment says (the container's session-start dep sync / setuptools / test runner).
_ENV_BACKSTOP = re.compile(
    r"(^|/)(\.venv|__pycache__|\.pytest_cache|\.ruff_cache|\.mypy_cache|"
    r"[^/]*\.egg-info|node_modules)(/|$)"
    r"|\.pyc$|(^|/)\.DS_Store$"
)

# latexmk / TeX build suffixes — regenerated by every compile.
_TEX_BACKSTOP = re.compile(
    r"\.(aux|bbl|blg|fdb_latexmk|fls|out|synctex\.gz|toc|lof|lot|nav|snm|vrb)$"
)


def _extract_command(comment: str) -> str:
    """Pull a regen command hint out of a comment block, if one is named."""
    m = re.search(r"`([^`]+)`", comment)
    if m:
        return m.group(1).strip()
    m = re.search(r"(scripts/[\w./-]+\.py|[\w./-]+\.py|uv (?:pip |)[\w -]+)", comment)
    if m:
        return m.group(1).strip()
    return ""


class GitignoreModel:
    """The ~87 rules, each with the comment block above it and a regenerable verdict."""

    def __init__(self, root: Path):
        self.root = root
        self.rules: list[dict] = []          # {line, pattern, comment, regenerable, command}
        self._regen_lines: set[int] = set()
        self._load()

    def _load(self) -> None:
        gi = self.root / ".gitignore"
        if not gi.is_file():
            return
        lines = gi.read_text(encoding="utf-8").splitlines()
        comment_block: list[str] = []
        for i, raw in enumerate(lines, start=1):
            s = raw.strip()
            if not s:
                comment_block = []
                continue
            if s.startswith("#"):
                comment_block.append(s.lstrip("# ").rstrip())
                continue
            # a pattern line
            inline = ""
            comment = " ".join(comment_block)
            regen = any(k in comment.lower() for k in _REGEN_KEYWORDS) or any(
                k in inline.lower() for k in _REGEN_KEYWORDS
            )
            command = _extract_command(comment)
            self.rules.append({
                "line": i, "pattern": s, "comment": comment,
                "regenerable": regen, "command": command,
            })
            if regen:
                self._regen_lines.add(i)
            # a comment block only annotates the immediately following pattern run;
            # keep it across consecutive pattern lines (a block often covers a group),
            # reset only on a blank line (handled above).

    def rule_count(self) -> int:
        return len(self.rules)

    def is_reconstructable(self, rel: str, attribution: dict[str, tuple[str, int, str]] | None = None) -> tuple[bool, str]:
        """(reconstructable?, reason). Env/build/TeX backstops, then the rule's comment."""
        if _ENV_BACKSTOP.search(rel):
            return True, "env/build/tooling artifact (session-start dep sync / setuptools / test runner)"
        if _TEX_BACKSTOP.search(rel):
            return True, "latexmk build artifact (regenerated by every compile)"
        attribution = attribution if attribution is not None else attribute_rules(self.root, [rel])
        hit = attribution.get(rel)
        if hit is not None:
            _src, ln, _pat = hit
            for r in self.rules:
                if r["line"] == ln and r["regenerable"]:
                    cmd = f" [{r['command']}]" if r["command"] else ""
                    return True, f".gitignore:{ln} documents regen{cmd}"
        return False, ""


# ---------------------------------------------------------------------------
# read-surface derivation
# ---------------------------------------------------------------------------

# directories/files whose CONTENT the pipeline reads (prefix match). Anything that
# lands under a read dir, or equals a read file, is "in the read-surface".
_REGISTRY_DIR_ATTRS = (
    "project_dir", "manuscript_dir", "tex_root", "target_dir",
    "briefs_dir", "versions_dir", "evolutions_dir", "loop_dir",
)
_REGISTRY_FILE_ATTRS = (
    "ledger", "plan_path", "glossary", "bib", "feedback_ledger",
)
# input paths that a fresh clone MUST carry (tracked); everything else the registry
# names is a pipeline-PRODUCED artifact (reconstructable when absent).
_INPUT_ATTRS = ("ledger", "plan_path", "glossary", "bib", "tex_root")


def registry_surface(root: Path) -> dict:
    """Registry layout contract → read-surface. Live import; HEAD-parse fallback.

    Returns {dirs:[rel], files:[rel], entries:[{path,source,attr,project,is_input}]}.
    """
    dirs: set[str] = set()
    files: set[str] = set()
    entries: list[dict] = []

    projects = _load_projects(root)
    stage_keys = _load_stage_keys(root)
    for name, proj in projects.items():
        for attr in _REGISTRY_DIR_ATTRS:
            rel = getattr(proj, attr, "") or ""
            if rel:
                dirs.add(rel.rstrip("/"))
                entries.append({"path": rel, "source": f"registry.{attr}",
                                "attr": attr, "project": name,
                                "is_input": attr in _INPUT_ATTRS})
        for attr in _REGISTRY_FILE_ATTRS:
            rel = getattr(proj, attr, "") or ""
            if rel:
                files.add(rel)
                entries.append({"path": rel, "source": f"registry.{attr}",
                                "attr": attr, "project": name,
                                "is_input": attr in _INPUT_ATTRS})
        for key in stage_keys:
            sp = proj.stage_path(key, root) if hasattr(proj, "stage_path") else None
            if sp is None:
                continue
            try:
                rel = str(Path(sp).resolve().relative_to(root.resolve()))
            except ValueError:
                continue
            files.add(rel)
            entries.append({"path": rel, "source": f"registry.stage:{key}",
                            "attr": f"stage:{key}", "project": name, "is_input": False})
    return {"dirs": sorted(dirs), "files": sorted(files), "entries": entries}


def _load_projects(root: Path) -> dict:
    """registry.all_projects() live; on import failure, a minimal HEAD-parsed stand-in."""
    src = root / "src"
    added = False
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
        added = True
    try:
        import importlib

        from laplace.pipeline import registry as _reg  # type: ignore
        importlib.reload(_reg)
        return _reg.all_projects()
    except Exception:
        return _head_projects(root)
    finally:
        if added:
            try:
                sys.path.remove(str(src))
            except ValueError:
                pass


def _load_stage_keys(root: Path) -> list[str]:
    try:
        from laplace.pipeline import schema as _schema  # type: ignore
        return list(_schema.STAGE_ARTIFACTS.keys())
    except Exception:
        txt = head_source(root, "src/laplace/pipeline/schema.py") or ""
        m = re.search(r"STAGE_ARTIFACTS\s*=\s*\{(.*?)\}", txt, re.S)
        return re.findall(r'"([^"]+)"\s*:', m.group(1)) if m else []


class _StubProject:
    """A registry stand-in built from HEAD when the live import is broken."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def stage_path(self, key, repo_root=None):  # noqa: D401 - matches Project API
        return None


def _head_projects(root: Path) -> dict:
    """Degraded registry surface: the registry_projects.json data rows (from HEAD) +
    the documented convention.

    Parsed as JSON, not regex-scraped out of a source file: the project rows became
    DATA on 2026-08-04 (the hardcoded corpus dict this used to scrape is deleted), so
    the degraded surface reads the same file the live registry reads. A row's own
    ``tex_root`` is honoured — the convention below is the fallback for a row that
    declares none, exactly as ``registry._build_registry`` treats it."""
    try:
        data = json.loads(head_source(root, "registry_projects.json") or "")
    except ValueError:
        data = {}
    rows = data.get("projects") if isinstance(data, dict) else data
    rows = [r for r in rows if isinstance(r, dict) and r.get("name")] \
        if isinstance(rows, list) else []
    projs: dict = {}
    for row in rows:
        name = row["name"]
        pd = f"synthetics papers/{name}"
        ms = f"{pd}/manuscript"
        projs[name] = _StubProject(
            name=name, project_dir=pd, manuscript_dir=ms,
            tex_root=row.get("tex_root") or ms,
            ledger=f"corpus_friction/{name}.jsonl", plan_path=f"{ms}/projection_plan.json",
            target_dir=f"{ms}/whitepaper", briefs_dir=f"{ms}/briefs",
            glossary=f"{pd}/GLOSSARY.md", bib="corpus/corpus.bib",
            feedback_ledger=f"{ms}/whitepaper/feedback/feedback.jsonl",
            versions_dir=f"{ms}/versions", evolutions_dir=f"{ms}/evolutions", loop_dir="",
        )
    projs["paper_eigen"] = _StubProject(
        name="paper_eigen", project_dir="paper_eigen",
        manuscript_dir="paper_eigen/manuscript", target_dir="paper_eigen/manuscript",
        loop_dir="paper_eigen/_loop", bib="corpus/corpus.bib",
        tex_root="", ledger="", plan_path="", glossary="", feedback_ledger="",
        briefs_dir="", versions_dir="", evolutions_dir="",
    )
    projs["eigenengine"] = _StubProject(
        name="eigenengine", project_dir="eigenengine",
        manuscript_dir="eigenengine/manuscript", target_dir="eigenengine/manuscript",
        bib="eigenengine/manuscript/refs.bib", tex_root="", ledger="", plan_path="",
        glossary="", feedback_ledger="", briefs_dir="", versions_dir="",
        evolutions_dir="", loop_dir="",
    )
    return projs


# --- static scan for repo-relative path literals ---------------------------

_SCAN_GLOBS = (
    "src/laplace/pipeline/**/*.py",
    "src/laplace/manuscript/storyboard.py",
    "src/laplace/web/scanner.py",
    "src/laplace/manuscript/review_surface.py",
    ".claude/workflows/*.js",
    ".claude/workflows/*.py",
)
# a repo-root runtime dotfile the pipeline resolves at the root (e.g. .nodemap.json)
_ROOT_DOTFILE = re.compile(r"^\.[\w.-]+\.(json|jsonl|log|npz)$")
_JS_STR = re.compile(r"""(['"`])((?:\\.|(?!\1).)*)\1""")


def _string_literals_py(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _string_literals_regex(text)
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
        elif isinstance(node, ast.JoinedStr):  # f-string: keep the static leading text
            lead = ""
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    lead += v.value
                else:
                    break
            if lead:
                out.append(lead)
    return out


def _string_literals_regex(text: str) -> list[str]:
    return [m.group(2) for m in _JS_STR.finditer(text)]


def _is_repo_path_literal(s: str, toplevel: set[str]) -> str | None:
    """Return the repo-relative path a literal denotes, or None if it is not one."""
    if not s or len(s) > 200 or "\n" in s:
        return None
    s = s.strip()
    # static leading part only (drop anything from the first format placeholder on)
    lead = re.split(r"[{$]", s, maxsplit=1)[0]
    if "/" in lead:
        first = lead.split("/", 1)[0]
        if first in toplevel and lead.count("/") >= 1 and not lead.endswith("/"):
            # a concrete-prefixed path (config, workflow script, ...)
            if re.search(r"\.[A-Za-z0-9]{1,6}$", lead):
                return lead
    # a repo-root runtime dotfile referenced by bare name
    if "/" not in s and _ROOT_DOTFILE.match(s) and s in toplevel:
        return s
    return None


def static_surface(root: Path) -> dict:
    """Path literals from the organs/surfaces/workflows that name a concrete repo file."""
    toplevel = set(os.listdir(root))
    found: dict[str, list[str]] = {}
    for pat in _SCAN_GLOBS:
        for path in sorted(root.glob(pat)):
            rel = str(path.relative_to(root))
            text = None
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
            if path.suffix == ".py":
                lits = _string_literals_py(text) if text is not None else []
                if not lits:  # mid-edit / unparsable -> committed state
                    head = head_source(root, rel)
                    if head:
                        lits = _string_literals_py(head)
            else:
                lits = _string_literals_regex(text or "")
                if not lits:
                    head = head_source(root, rel)
                    if head:
                        lits = _string_literals_regex(head)
            for lit in lits:
                p = _is_repo_path_literal(lit, toplevel)
                if p:
                    found.setdefault(p, [])
                    if rel not in found[p]:
                        found[p].append(rel)
    entries = [{"path": p, "source": "static", "read_by": srcs} for p, srcs in sorted(found.items())]
    return {"files": sorted(found), "entries": entries}


# ---------------------------------------------------------------------------
# classifier
# ---------------------------------------------------------------------------


def classify_path(rel: str, tracked: set[str], ignored: set[str],
                  is_reconstructable) -> str:
    """Pure classifier. ``is_reconstructable`` is ``rel -> bool``.

    tracked          -> in git.
    reconstructable  -> not tracked but regenerable (documented regen / build artifact),
                        OR absent and produced by the pipeline at run time.
    violation        -> present, ignored, read, and with no regen path.
    """
    if rel in tracked:
        return "tracked"
    if is_reconstructable(rel):
        return "reconstructable"
    if rel in ignored:
        return "violation"
    # not tracked, not ignored, not reconstructable-by-name => absent artifact the
    # pipeline writes on its own run; a fresh clone rebuilds it identically.
    return "reconstructable"


def _dir_has_tracked(rel_dir: str, tracked: set[str]) -> bool:
    pfx = rel_dir.rstrip("/") + "/"
    return any(t == rel_dir or t.startswith(pfx) for t in tracked)


def _in_read_surface(rel: str, surface_dirs: set[str], surface_files: set[str]) -> bool:
    if rel in surface_files:
        return True
    return any(rel == d or rel.startswith(d.rstrip("/") + "/") for d in surface_dirs)


# ---------------------------------------------------------------------------
# the audit
# ---------------------------------------------------------------------------


def audit(root: Path) -> dict:
    root = Path(root).resolve()
    tracked = tracked_files(root)
    ignored = ignored_present_files(root)
    gi = GitignoreModel(root)

    reg = registry_surface(root)
    stat = static_surface(root)

    surface_dirs = set(reg["dirs"])
    surface_files = set(reg["files"]) | set(stat["files"])

    # -- the sharp test: ignored-present files that lie in the read-surface ----
    in_surface_ignored = sorted(
        f for f in ignored if _in_read_surface(f, surface_dirs, surface_files)
    )
    attribution = attribute_rules(root, in_surface_ignored)

    def _recon(rel: str) -> bool:
        ok, _reason = gi.is_reconstructable(rel, attribution)
        return ok

    intersection = []
    violations = []
    for f in in_surface_ignored:
        ok, reason = gi.is_reconstructable(f, attribution)
        cls = "reconstructable" if ok else "violation"
        src, ln, pat = attribution.get(f, ("", 0, ""))
        rec = {"path": f, "class": cls, "reason": reason or "no documented regen path",
               "gitignore_line": ln, "gitignore_pattern": pat}
        intersection.append(rec)
        if not ok:
            violations.append({"path": f, "rule": f".gitignore:{ln} {pat}",
                               "reason": "read by pipeline · present · ignored · no regen path"})

    # -- classify the declared surface ENTRIES (contract-level view) -----------
    n_tracked = n_recon = 0
    entry_class: list[dict] = []
    for e in reg["entries"]:
        rel = e["path"].rstrip("/")
        if e["path"] in tracked or _dir_has_tracked(rel, tracked):
            cls = "tracked"
            n_tracked += 1
        else:
            # a produced/absent registry artifact -> reconstructable by the pipeline
            cls = classify_path(rel, tracked, ignored, _recon)
            if cls == "reconstructable":
                n_recon += 1
        entry_class.append({**e, "class": cls})
    for e in stat["entries"]:
        rel = e["path"]
        cls = classify_path(rel, tracked, ignored, _recon)
        if cls == "tracked":
            n_tracked += 1
        elif cls == "reconstructable":
            n_recon += 1
        entry_class.append({**e, "class": cls})

    # -- per-rule gitignore findings ------------------------------------------
    findings = []
    by_line: dict[int, list[dict]] = {}
    for rec in intersection:
        by_line.setdefault(rec["gitignore_line"], []).append(rec)
    for r in gi.rules:
        hidden = by_line.get(r["line"], [])
        if not hidden:
            continue
        findings.append({
            "gitignore_line": r["line"], "pattern": r["pattern"],
            "comment_regenerable": r["regenerable"], "command": r["command"],
            "hides_read_surface": [h["path"] for h in hidden],
            "violations": [h["path"] for h in hidden if h["class"] == "violation"],
        })

    read_surface_size = len(reg["entries"]) + len(stat["entries"])
    report = {
        "read_surface_size": read_surface_size,
        "read_surface": {
            "registry_dirs": reg["dirs"],
            "registry_files": reg["files"],
            "static_literals": stat["files"],
            "projects": sorted({e["project"] for e in reg["entries"]}),
        },
        "classified": {
            "tracked": n_tracked,
            "reconstructable": n_recon + sum(1 for r in intersection if r["class"] == "reconstructable"),
            "violations": len(violations),
        },
        "intersection": intersection,      # in-surface ignored-present files, classified
        "violations": violations,
        "gitignore_rule_count": gi.rule_count(),
        "gitignore_findings": findings,
        "entries": entry_class,
    }
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _human_summary(rep: dict) -> str:
    c = rep["classified"]
    lines = [
        "surfacing audit — pipeline read-surface vs a fresh clone",
        f"  read-surface entries : {rep['read_surface_size']} "
        f"({len(rep['read_surface']['registry_dirs'])} registry dirs, "
        f"{len(rep['read_surface']['registry_files'])} registry files, "
        f"{len(rep['read_surface']['static_literals'])} static literals; "
        f"{len(rep['read_surface']['projects'])} projects)",
        f"  .gitignore rules     : {rep['gitignore_rule_count']}",
        f"  classified           : tracked={c['tracked']} "
        f"reconstructable={c['reconstructable']} violations={c['violations']}",
    ]
    if rep["intersection"]:
        lines.append("  ignored-present files inside the read-surface:")
        for r in rep["intersection"]:
            lines.append(f"    [{r['class']:15s}] {r['path']}  ({r['reason']})")
    else:
        lines.append("  no ignored-present files intersect the read-surface")
    if rep["violations"]:
        lines.append("  VIOLATIONS (invisible to a fresh clone, no regen path):")
        for v in rep["violations"]:
            lines.append(f"    ! {v['path']}  [{v['rule']}]")
    else:
        lines.append("  VIOLATIONS: none — nothing load-bearing hides behind .gitignore")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", default=".", help="repo root (default: cwd)")
    ap.add_argument("--json", dest="json_out", default=None, help="write JSON report here")
    ap.add_argument("-q", "--quiet", action="store_true", help="suppress human summary")
    a = ap.parse_args(argv)

    rep = audit(Path(a.root))
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    if not a.quiet:
        print(_human_summary(rep))
    if a.json_out is None and a.quiet:
        print(json.dumps(rep, ensure_ascii=False))
    return 2 if rep["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
