"""self_shard.py - shard the WHOLE directory into the graded conceptric.

The generalisation of ``self_corpus`` from the five engine-self files to every semantic tracked
file in the repo - the bootstrap of the goal (self-store the directory, grade by grade,
surfacing at a word, reconstructing faithfully-enough). ``self_corpus`` reconstructs the
*self* (the five hand-maintained files); this reconstructs the *directory* (all 569), the
same conjugate operation widened to the whole tree. There is one thing.

Opaque Atlas authority payloads are deliberately not semantic leaves. Thin ledgers and
content-addressed hive chunks travel through Git/custody, while their manifests and receipts remain
in this map. Embedding thousands of compressed event bodies would confuse storage morphology with
meaning and make a repour inflate its own routing substrate.

The store is the TRACE - nodes + edges within and between grades, NOT the text. Each object
is one node carrying:

  * grade 0 - the HANDLE: filename + a one-line essence + the keyword tokens it *surfaces at*.
              The "surface at a word" slice; bounded, one entry per object; this is what the
              index persists.
  * grade 1 - the SPINE: the structure (md headings / py def+class signatures / tex sections),
              RECONSTRUCTED by re-reading the source on descent.
  * grade 2 - the SOURCE: the full content, RECONSTRUCTED by re-reading - only the pointer is
              stored; text is never duplicated into the conceptric.

Edges (the wiring that makes the directory one conceptric, not 569 islands):

  * descend (intra-object): grade 0 -> 1 -> 2, the embedded reconstructor (fired on demand).
  * link (inter-object): ``[[wikilinks]]`` + repo-file links (md), ``laplace.X`` imports (py),
    ``\\input`` / ``\\cite`` (tex).

The soul covenant is ABSOLUTE: ``soul/*`` nodes carry a path ref only - no essence drawn from
content, no spine, no content, at any grade (refs only, never content - META_TEST_2026-06-05,
``Canon.route``). The sharder never even reads a soul file.

``reconstruct_by_name(query, grade)`` is the conjugate read: a word surfaces the grade-0 handle,
and descending RE-READS the pointed-at source for spine/content - reconstruction, not a stored
copy. ``shard_faithfulness`` is the retrieval-closure gate: does every handle get back to its
source, and does an object surface at its own word (factual faithfulness = retrieval, not
re-derivation - the life_corpus floor, N11)?

Conjecture, seams showing - the first rung of the directory-as-its-own-corpus. No LLM here: the
sharding is deterministic extraction; the LLM firing is the descent the orchestrator performs
against the meter, exactly as in ``self_corpus``. Built smallest-real-thing first.
"""

from __future__ import annotations
from laplace.core.checkout import repo_root as _repo_root   # the serving checkout, as the scanner resolved it
from laplace.core.checkout import source_tree

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

# The conceptric's grade-0 projection of the directory (the handles + edges - the trace).
_INDEX = "SELF_SHARD_INDEX.md"
# The refs-only seal (F24, 2026-06-08): ``soul/`` (the transferred self) AND ``soul_corpus/sealed/``
# (the soul-dump distillate). A sealed node's CONTENT is never read, never inlined, at any grade. Its
# HANDLE (the path) MAY carry real identity - the privacy is the seal on the raw, not anonymisation of
# the structure, so the same person resolves across corpora (the author's reframe: the person on the
# paper and the person in the chat log are one entity; only the shard content stays private).
_SEALED_PREFIXES = ("soul/", "soul_corpus/sealed/")
_SOUL_PREFIX = _SEALED_PREFIXES[0]  # back-compat alias (was the only sealed zone)

# Extensions we open and extract structure from. Anything else is a name-only asset node
# (binaries, fonts, archives) - we never read it, so a .png never lands as mojibake.
_TEXT_EXT = {
    ".md", ".markdown", ".tex", ".py", ".json", ".yaml", ".yml", ".bib",
    ".txt", ".html", ".mjs", ".js", ".ts", ".css", ".toml", ".cfg", ".ini", ".sh",
}
_IGNORE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build",
}
_CONTENT_CAP = 4000   # grade-2 content slice; the pointer is authoritative, not this copy.


# ---------------------------------------------------------------------------
# The tracked set
# ---------------------------------------------------------------------------

def _is_opaque_authority_payload(relative: str) -> bool:
    """Keep Atlas payload custody out of the semantic self projection.

    The filter is independent of ``.gitignore``: these files MUST remain trackable because they
    are authority. Only the derived semantic view omits them. Human-readable receipts and
    manifests beside them continue through the ordinary sharder.
    """

    parts = tuple(part for part in relative.replace("\\", "/").split("/") if part)
    if len(parts) < 4 or parts[:2] != ("atlas", "stores"):
        return False
    if "hives" in parts[3:]:
        return True
    return parts[-1].endswith((".sqlite3", ".sqlite3-shm", ".sqlite3-wal"))


def _semantic_paths(repo_root: Path, relatives: list[str]) -> list[Path]:
    return [
        repo_root / relative
        for relative in relatives
        if not _is_opaque_authority_payload(relative)
    ]

def _tracked_files(repo_root: Path) -> list[Path]:
    """The repo's files as the LIVE self: tracked PLUS untracked-but-not-ignored (the working
    tree). A node WRITTEN this session - a freshly materialised soul handle, a new manuscript -
    is part of the self the moment it lands, before it is committed; this is what lets the brain
    scanner watch the conceptric GROW during a run. Both git probes honour ``.gitignore`` exactly
    (``--exclude-standard``), so ``.venv`` and the sealed local tier stay out. Falls back to a
    pruned tree walk when git is absent (e.g. a tmp_path test tree)."""
    try:
        rels: list[str] = []
        seen: set[str] = set()
        for args in (["git", "ls-files"],
                     ["git", "ls-files", "--others", "--exclude-standard"]):
            out = subprocess.run(
                args, cwd=repo_root, capture_output=True, text=True, timeout=30, check=True,
            )
            for ln in out.stdout.splitlines():
                r = ln.strip()
                if r and r not in seen:
                    seen.add(r)
                    rels.append(r)
        if rels:
            return _semantic_paths(repo_root, rels)
    except (OSError, subprocess.SubprocessError):
        pass
    files: list[Path] = []
    for root, dirs, names in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for n in names:
            path = Path(root) / n
            try:
                relative = path.relative_to(repo_root).as_posix()
            except ValueError:
                continue
            if not _is_opaque_authority_payload(relative):
                files.append(path)
    return files


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _rel(repo_root: Path, path: Path) -> str:
    """The repo-relative name, by string slice against the root prefix.

    Was ``path.relative_to(repo_root)``. ``shard_repo`` calls this twice per tracked file -
    29,514 calls per deposit - and ``relative_to`` builds a fresh ``PurePath`` and walks its
    parts each time: 0.956s against 0.015s for the slice on the same call set (66x, R-A2,
    load 2.7; the census banked 196x at load ~11). The under-root guard ``relative_to``
    provides is kept verbatim - a path outside the root still raises ``ValueError``, which
    ``shard_repo`` catches - and the root itself still names itself ``.``. A RELATIVE root
    (``Path('.')``, which is what a ``--repo-root .`` default resolves to) has no prefix to
    strip: the walked path is already the name, and an absolute path is not under it - the
    same ValueError pathlib raises. (WO-20260820-rel-string-slice.)"""
    s = str(path)
    r = str(repo_root)
    if r == ".":
        if os.path.isabs(s):
            raise ValueError(f"{s!r} is not in the subpath of {r!r}")
        return s.replace("\\", "/")
    prefix = r if r.endswith(os.sep) else r + os.sep
    if not s.startswith(prefix):
        if s == r:
            return "."
        raise ValueError(f"{s!r} is not in the subpath of {r!r}")
    return s[len(prefix):].replace("\\", "/")


def _is_soul(rel: str) -> bool:
    """True for a refs-only sealed node (``soul/`` or ``soul_corpus/sealed/``): content withheld at
    every grade. The handle/path may still bear identity (the cross-corpus entity key)."""
    return rel.startswith(_SEALED_PREFIXES)


# ---------------------------------------------------------------------------
# Extraction - essence (grade 0), spine (grade 1), edges (the wiring)
# ---------------------------------------------------------------------------

_JSON_PARSE_CAP = 200_000   # chars; measured, see _json_essence


def _json_essence(text: str) -> str:
    """The grade-0 handle for a JSON object: its top-level keys, or its shape.

    SIZE-GATED (2026-08-20, WO-20260820-kmeans-is-the-new-bottleneck's sibling cure). Parsing was
    unconditional, and the cost is carried by a handful of giants: of 1,613 tracked JSONs, the 93
    over 200 KB cost **7.05 s** to parse and the other 1,520 cost **0.24 s**. A key list is a
    HANDLE - it is worth 0.16 ms, not 76 ms. Above the cap the essence states the size instead of
    the keys: deterministic in the file's own content, so the committed index stays stable across
    rebuilds, and the descent still re-reads the source for anything deeper (grade 1 keeps the real
    key spine - ``_spine`` is untouched)."""
    if len(text) > _JSON_PARSE_CAP:
        return (f"large json document ({len(text) // 1024} KiB, over the "
                f"{_JSON_PARSE_CAP // 1024} KiB handle-parse cap - keys read on descent)")
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return "json document"
    if isinstance(data, dict):
        keys = list(data.keys())
        return ("keys: " + ", ".join(map(str, keys[:8]))) if keys else "json object"
    if isinstance(data, list):
        return f"json array [{len(data)}]"
    return "json scalar"


def _essence(path: Path, text: str) -> str:
    """A one-line handle - what the object IS, at a glance. Deterministic per file type."""
    ext = path.suffix.lower()
    if ext == ".py":
        m = re.search(r'^\s*[ru]?"""(.*?)(?:"""|$)', text, re.S | re.M)
        if m:
            head = [ln.strip() for ln in m.group(1).strip().splitlines() if ln.strip()]
            if head:
                return head[0][:160]
        m = re.search(r'^(?:async\s+def|def|class)\s+\w+', text, re.M)
        return m.group(0).strip() if m else "python module"
    if ext in (".md", ".markdown"):
        # Frontmatter description OUTRANKS the H1: a canon SKILL.md's H1 is its own
        # NAME, so the H1-essence carried zero task content and the skills fibre was
        # unreachable by claimed task (measured 2026-08-21: welder's vector was pure
        # path tokens, in-cluster rank 34/34; claimed-task essence -> R 0.5185 to 0.0,
        # 54/54 rank-1 - WO-20260821-skill-essence-is-its-own-name).
        if text.startswith("---"):
            fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
            if fm:
                d = re.search(r'^description:\s*(?:>-?\s*\n((?:[ \t]+.+\n?)+)|(.+)$)',
                              fm.group(1), re.M)
                if d:
                    val = d.group(2) or " ".join(
                        ln.strip() for ln in (d.group(1) or "").splitlines())
                    val = val.strip().strip('"').strip("'")
                    if val:
                        return val[:160]
        m = re.search(r'^#\s+(.+)$', text, re.M)
        if m:
            return m.group(1).strip()[:160]
        for ln in text.splitlines():
            s = ln.strip()
            if s and not s.startswith(("---", "<!--", "#")):
                return s[:160]
        return "markdown document"
    if ext == ".tex":
        m = re.search(r'\\title\{(.+?)\}', text, re.S)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()[:160]
        m = re.search(r'\\(?:sub)*section\*?\{(.+?)\}', text)
        if m:
            return m.group(1).strip()[:160]
        for ln in text.splitlines():
            s = ln.strip()
            if s and not s.startswith("%"):
                return s[:160]
        return "latex source"
    if ext == ".json":
        return _json_essence(text)
    if ext in (".yaml", ".yml"):
        keys = list(dict.fromkeys(re.findall(r"^([A-Za-z_][\w-]*):", text, re.M)))
        return ("keys: " + ", ".join(keys[:8])) if keys else "yaml document"
    if ext == ".bib":
        n = len(re.findall(r"^@\w+\{", text, re.M))
        return f"{n} bib reference(s)"
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return first[:160] if first else f"{ext.lstrip('.') or 'data'} file"


_SPINE_JSON_PARSE_CAP = 1_000_000   # chars; measured, see _spine


def _spine(path: Path, text: str, *,
           json_cap: int | None = _SPINE_JSON_PARSE_CAP) -> list[str]:
    """The structure - the grade-1 deltas, reconstructed by re-reading on descent.

    SIZE-GATED IN THE SHARD PATH ONLY (2026-08-20, WO-20260820-spine-parses-655mb-to-count-keys,
    and the ruling asked for by WO-20260820-spine-parses-the-giants-too). ``shard_file`` consumes
    nothing but ``len(...)`` of this list, yet the .json branch parsed 655.7 MB of tracked JSON
    every deposit to get it: of 1,645 tracked .json files the 45 over 1 MB cost **4.62s** and the
    other 1,600 cost **0.26s** (R-A2, load 2.7; the census banked 7.89s at load ~11). Above the
    cap the branch returns ``[]`` - exactly what an unparseable file already returns - so
    ``spine_count`` for those 45 giants reads 0. Nothing routes on it: ``write_index`` never
    renders the field and ``load_index`` returns it as 0, so every shard reconstructed through the
    persisted trace already carries 0.

    THE RULING (the open half of WO-20260820-spine-parses-the-giants-too): grade-1 descent KEEPS
    THE REAL KEYS. ``_json_essence`` promises the reader "keys read on descent" in the grade-0
    handle of every giant, and a cap here would make that line a lie. ``_project_shard`` therefore
    passes ``json_cap=None`` - the parse is paid once, by the one caller who explicitly descended
    onto that one file, instead of 45 times per deposit by a caller that only counts."""
    ext = path.suffix.lower()
    if ext == ".py":
        return [m.strip() for m in re.findall(r"^(?:async\s+def|def|class)\s+[^\n:(]+", text, re.M)]
    if ext in (".md", ".markdown"):
        return [ln.strip() for ln in text.splitlines() if re.match(r"^#{1,6}\s", ln)]
    if ext == ".tex":
        return [m.strip() for m in re.findall(r"^\\(?:(?:sub)*section\*?|chapter|input)\{[^}]*\}", text, re.M)]
    if ext in (".yaml", ".yml"):
        return list(dict.fromkeys(re.findall(r"^([A-Za-z_][\w-]*):", text, re.M)))
    if ext == ".json":
        if json_cap is not None and len(text) > json_cap:
            return []
        try:
            data = json.loads(text)
        except (ValueError, RecursionError):
            return []
        return list(map(str, data.keys())) if isinstance(data, dict) else []
    return []


def _edges(path: Path, text: str) -> list[dict[str, str]]:
    """The inter-object wiring: links (md), imports (py), input/cite (tex). Deduped, capped."""
    ext = path.suffix.lower()
    raw: list[tuple[str, str]] = []
    if ext in (".md", ".markdown"):
        raw += [("link", m.strip()) for m in re.findall(r"\[\[([^\]]+)\]\]", text)]
        for m in re.findall(r"\]\(([^)]+)\)", text):
            t = m.strip().split("#")[0]
            if t and not t.startswith(("http://", "https://", "mailto:", "data:")):
                raw.append(("link", t))
    elif ext == ".py":
        raw += [("import", m) for m in re.findall(r"^\s*from\s+laplace\.([\w.]+)\s+import", text, re.M)]
        raw += [("import", m) for m in re.findall(r"^\s*import\s+laplace\.([\w.]+)", text, re.M)]
    elif ext == ".tex":
        raw += [("input", m.strip()) for m in re.findall(r"\\input\{([^}]+)\}", text)]
        for m in re.findall(r"\\cite[tp]?\{([^}]+)\}", text):
            raw += [("cite", k.strip()) for k in m.split(",") if k.strip()]
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for kind, to in raw:
        key = (kind, to)
        if to and key not in seen:
            seen.add(key)
            out.append({"kind": kind, "to": to})
        if len(out) >= 40:
            break
    return out


def _keywords(rel: str, essence: str) -> list[str]:
    """The words the object surfaces at - from its path stem and its essence."""
    from laplace.pipeline.canon import _tokenize

    toks = _tokenize(rel.replace("/", " ").replace("_", " ").replace("-", " "))
    toks |= _tokenize(essence)
    toks.discard("md")
    return sorted(toks)[:12]


# ---------------------------------------------------------------------------
# The shard - one node per object
# ---------------------------------------------------------------------------

def shard_file(repo_root: Path | str, path: Path) -> dict[str, Any]:
    """One object -> one graded node. Soul stays sealed (never read); binaries stay name-only."""
    repo_root = Path(repo_root)
    rel = _rel(repo_root, path)
    ext = path.suffix.lower()

    if _is_soul(rel):
        from laplace.pipeline.canon import _tokenize
        kws = sorted({"soul"} | _tokenize(rel.replace("/", " ").replace("_", " ")))
        return {
            "name": rel, "kind": "soul", "essence": "(sealed soul fragment - refs only)",
            "keywords": kws[:12], "spine_count": 0, "lines": 0, "edges": [], "sealed": True,
        }

    if ext not in _TEXT_EXT:
        return {
            "name": rel, "kind": ext.lstrip(".") or "data",
            "essence": f"{ext.lstrip('.') or 'data'} asset", "keywords": _keywords(rel, ""),
            "spine_count": 0, "lines": 0, "edges": [], "sealed": False,
        }

    text = _read_text(path)
    essence = _essence(path, text)
    return {
        "name": rel, "kind": ext.lstrip("."), "essence": essence,
        "keywords": _keywords(rel, essence), "spine_count": len(_spine(path, text)),
        "lines": (text.count("\n") + 1) if text else 0, "edges": _edges(path, text),
        "sealed": False,
    }


def shard_repo(repo_root: Path | str) -> dict[str, dict[str, Any]]:
    """Shard every tracked file into a name -> graded-node map (the conceptric's grade-0 layer)."""
    repo_root = Path(repo_root)
    shards: dict[str, dict[str, Any]] = {}
    for p in _tracked_files(repo_root):
        try:
            if not p.is_file():
                continue
            shards[_rel(repo_root, p)] = shard_file(repo_root, p)
        except (OSError, ValueError):
            continue
    return shards


# ---------------------------------------------------------------------------
# Reconstruct-by-name - the conjugate read (a word -> the object, descend re-reads source)
# ---------------------------------------------------------------------------

def _project_shard(repo_root: Path, sh: dict[str, Any], grade: int) -> dict[str, Any]:
    """Project one node at a grade. grade 1/2 RE-READ the source - the store holds the
    handle + pointer, never a text copy. The soul covenant holds at every grade."""
    out = {
        "name": sh["name"], "kind": sh["kind"], "essence": sh["essence"],
        "keywords": sh["keywords"], "edges": sh["edges"], "sealed": sh["sealed"],
    }
    if grade <= 0:
        return out
    if sh["sealed"]:
        out["note"] = "sealed soul fragment - refs only, never content, at any grade"
        return out
    path = repo_root / sh["name"]
    if path.suffix.lower() not in _TEXT_EXT:
        out["note"] = "binary asset - pointer only"
        out["pointer"] = {"path": sh["name"]}
        return out
    text = _read_text(path)
    if grade == 1:
        # json_cap=None: the descent is the one caller that asked for this file's keys, and the
        # grade-0 handle promised them ("keys read on descent"). See _spine's ruling.
        out["spine"] = _spine(path, text, json_cap=None)
        return out
    out["pointer"] = {"path": sh["name"], "lines": sh["lines"]}
    out["content"] = text[:_CONTENT_CAP]
    if len(text) > _CONTENT_CAP:
        out["content_truncated"] = True
    return out


def reconstruct_by_name(
    repo_root: Path | str, query: str, grade: int = 0,
    shards: dict[str, dict[str, Any]] | None = None, k: int = 3,
) -> dict[str, Any]:
    """Surface the object(s) a word reconstructs to, at a grade. Score = keyword overlap, with
    a path-substring boost so a near-exact name resolves first. Descending re-reads the source."""
    repo_root = Path(repo_root)
    # Reconstruct THROUGH the persisted trace when it exists (the conjugate read of write_index):
    # cheaper than re-sharding every tracked file on each call, and the whole point of persisting the
    # index. Fall back to a fresh shard when there is no index (e.g. a tmp test tree). Descent always
    # re-reads the source, so a slightly stale index never serves stale CONTENT - only the node set.
    if shards is None:
        shards = load_index(repo_root) or shard_repo(repo_root)
    from laplace.pipeline.canon import _tokenize

    q = _tokenize(query)
    ql = query.lower().strip()
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for name, sh in shards.items():
        score = len(q & set(sh["keywords"]))
        if ql and ql in name.lower():
            score += 5
        if score:
            scored.append((score, name, sh))
    scored.sort(key=lambda t: (-t[0], t[1]))
    top = scored[:k]
    matches = [_project_shard(repo_root, sh, grade) for _s, _n, sh in top]
    descend = None
    if grade < 2 and matches:
        descend = {
            "to_grade": grade + 1,
            "call": "re-read the matched object's source for its spine (g1) / content (g2)",
            "fire": f"reconstruct_by_name(repo_root, {query!r}, grade={grade + 1})",
        }
    return {
        "query": query, "grade": grade, "matches": matches, "descend": descend,
        "note": "a word -> the object's grade-k projection; deeper grades re-read the source "
                "(reconstruction, not a stored copy). Soul stays refs-only at every grade.",
    }


# ---------------------------------------------------------------------------
# The retrieval-closure gate - is the directory faithfully indexed?
# ---------------------------------------------------------------------------

def shard_faithfulness(
    repo_root: Path | str, shards: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Does every handle get back to its source, and does an object surface at its own word?

    The factual-faithfulness floor (N11): closure by RETRIEVAL, not re-derivation. The hard gate
    is structural - every pointer resolves, every non-binary has a handle, no soul leaks content,
    and every object is retrievable by its own name. Keyword-distinctiveness (does an object
    surface at its top *essence* word, not just its name?) is reported as a metric, not frozen as
    a bar from this first run.
    """
    repo_root = Path(repo_root)
    shards = shards if shards is not None else shard_repo(repo_root)
    issues: list[str] = []
    resolved = with_handle = name_roundtrip = 0

    for name, sh in shards.items():
        if (repo_root / name).exists():
            resolved += 1
        else:
            issues.append(f"unresolved pointer: {name}")
        if sh["sealed"]:
            with_handle += 1
            if "(sealed" not in sh["essence"] or sh["lines"] or sh["spine_count"] or sh["edges"]:
                issues.append(f"SOUL LEAK: {name} carries more than a sealed ref")
        elif sh["essence"]:
            with_handle += 1
        else:
            issues.append(f"empty handle: {name}")
        res = reconstruct_by_name(repo_root, name, grade=0, shards=shards, k=5)
        if any(m["name"] == name for m in res["matches"]):
            name_roundtrip += 1
        else:
            issues.append(f"name does not retrieve its own object: {name}")

    # Distinctiveness metric (soft): does an object surface at its strongest essence keyword?
    distinct = 0
    measured = 0
    for name, sh in shards.items():
        kws = [kw for kw in sh["keywords"] if kw not in name.lower()]
        if not kws:
            continue
        measured += 1
        res = reconstruct_by_name(repo_root, kws[0], grade=0, shards=shards, k=5)
        if any(m["name"] == name for m in res["matches"]):
            distinct += 1

    total = len(shards)
    passed = not issues
    return {
        "pass": passed,
        "files": total,
        "resolved": f"{resolved}/{total}",
        "with_handle": f"{with_handle}/{total}",
        "name_roundtrip": f"{name_roundtrip}/{total}",
        "keyword_distinctiveness": f"{distinct}/{measured}" if measured else "0/0",
        "sealed": sum(1 for s in shards.values() if s["sealed"]),
        "issues": issues[:20],
        "note": "retrieval-closure: pointers resolve + handles present + no soul leak + "
                "names retrieve their objects. Distinctiveness is a soft metric (N11/E8).",
    }


# ---------------------------------------------------------------------------
# Persist the grade-0 trace (the handles + edges; deeper grades re-read the source)
# ---------------------------------------------------------------------------

def write_index(repo_root: Path | str, shards: dict[str, dict[str, Any]] | None = None) -> Path:
    """Write ``SELF_SHARD_INDEX.md`` - the directory's grade-0 projection (handles + edges).
    This is the trace (nodes + edges), bounded to one line per object; grade-1 spine and
    grade-2 content are never written here - they are reconstructed from the source on descent."""
    repo_root = Path(repo_root)
    shards = shards if shards is not None else shard_repo(repo_root)
    sealed = sum(1 for s in shards.values() if s["sealed"])
    lines = [
        "# Self-shard index - the directory as a graded conceptric",
        "",
        "<!-- generated by laplace.engine.self_shard. The trace is nodes + edges, not text: this file "
        "holds the grade-0 HANDLE (essence + the words it surfaces at) and the inter-object "
        "edges. grade-1 (spine) and grade-2 (content) are RECONSTRUCTED by re-reading the "
        "pointed-at source - reconstruction, never a stored copy. Soul is refs-only. -->",
        "",
        f"_{len(shards)} objects sharded ({sealed} sealed soul fragment(s), refs-only)._",
        "",
    ]
    for name in sorted(shards):
        sh = shards[name]
        kw = " ".join(sh["keywords"][:6])
        size = f" · {sh['lines']} lines" if sh["lines"] else ""
        edge = ""
        if sh["edges"]:
            edge = " · →" + ", ".join(f"{e['kind']}:{e['to']}" for e in sh["edges"][:8])
        lines.append(
            f"<!-- shard name:{name} kind:{sh['kind']} grade:0 sealed:{int(sh['sealed'])} -->"
        )
        lines.append(f"- **{name}** - {sh['essence']} · `{kw}`{size}{edge}")
    (repo_root / _INDEX).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return repo_root / _INDEX


# ---------------------------------------------------------------------------
# Read-back - the conjugate of write_index (the trace was write-only until now)
# ---------------------------------------------------------------------------

_SHARD_COMMENT_RE = re.compile(
    r"<!--\s*shard name:(?P<name>.+?) kind:(?P<kind>\S+) grade:\d+ sealed:(?P<sealed>[01])\s*-->"
)


def _parse_bullet(name: str, kind: str, sealed: bool, bullet: str) -> dict[str, Any]:
    """Parse one ``- **name** - essence · `kw` · N lines · →kind:to`` bullet back into a node.
    The inverse of the line ``write_index`` emits; soul stays sealed (the essence is forced to the
    sealed marker regardless of what the line carried, so a tampered index can never leak content)."""
    body = bullet.strip()
    prefix = f"- **{name}** - "
    if body.startswith(prefix):
        body = body[len(prefix):]
    elif body.startswith("- **") and "** - " in body:
        body = body.split("** - ", 1)[1]
    # The keyword field (always emitted, in backticks) is the unambiguous boundary after the
    # essence, so split THERE - not on every " · " - or an essence that itself contains the middot
    # separator truncates on read-back (the blind clean-room catch, N21).
    marker = body.find(" · `")
    essence, rest = (body[:marker], body[marker + 3:]) if marker >= 0 else (body, "")
    keywords: list[str] = []
    lines = 0
    edges: list[dict[str, str]] = []
    for p in (x.strip() for x in rest.split(" · ")):
        if p.startswith("`") and p.endswith("`"):
            keywords = p.strip("`").split()
        elif p.endswith("lines"):
            mnum = re.match(r"(\d+)\s+lines", p)
            if mnum:
                lines = int(mnum.group(1))
        elif p.startswith("→"):  # the → edge list
            for tok in p[1:].split(", "):
                kpart, sep, to = tok.partition(":")
                if sep and to.strip():
                    edges.append({"kind": kpart.strip(), "to": to.strip()})
    essence = essence.strip()
    return {
        "name": name, "kind": kind,
        "essence": "(sealed soul fragment - refs only)" if sealed else essence,
        "keywords": keywords, "spine_count": 0, "lines": lines,
        "edges": [] if sealed else edges, "sealed": sealed,
    }


def load_index(repo_root: Path | str) -> dict[str, dict[str, Any]]:
    """Read the persisted grade-0 trace (``SELF_SHARD_INDEX.md``) BACK into shards.

    The conjugate of ``write_index`` - which was write-only until now, so the only way to get a
    ``shards`` map was to re-shard all 569 files. This makes the persisted conceptric usable: the
    hello / scanner reconstruct THROUGH the trace (addressing layer), re-reading source only on
    descent. Defensive: a missing or garbled index yields ``{}`` (never a hard dependency)."""
    repo_root = Path(repo_root)
    text = _read_text(repo_root / _INDEX)
    if not text:
        return {}
    lines = text.splitlines()
    shards: dict[str, dict[str, Any]] = {}
    for i, ln in enumerate(lines):
        m = _SHARD_COMMENT_RE.search(ln)
        if not m:
            continue
        name = m.group("name").strip()
        bullet = lines[i + 1] if i + 1 < len(lines) else ""
        shards[name] = _parse_bullet(name, m.group("kind").strip(), m.group("sealed") == "1", bullet)
    return shards


# ---------------------------------------------------------------------------
# The self-substrate - which conceptric nodes carry an engine-self role (ONE definition)
# ---------------------------------------------------------------------------

# The self within the directory conceptric. ONE definition (N21), consumed by BOTH the hello
# (``self_corpus.reconstruct_self``) and orient (``canon._route_self_knowledge``) - replacing the
# two hardcoded file lists that had drifted apart. The self is a discovered SUBSET of the
# conceptric, not a special-cased five-file read; a deleted file simply drops out, so the self
# degrades through the graph instead of crashing.
_SELF_ROLES = {
    "fixed_point": ["HANDOFF.md", "OPEN_STACK.md"],          # the grade-0 sources (what's now / next)
    "map": ["EIGEN_ARCHITECTURE.md", "EIGEN_DIARY.md"],      # the grade-2 deep map
    "protocol": ["EIGEN_PROTOCOL.md"],                       # the open/close ritual
    "guides": ["PIPELINE_GUIDE.md", "TECHNICAL_GUIDE.md"],   # operational how-to (dream-audit reach hole)
}
_HANDOFF_GLOB = "SESSION_HANDOFF_*.md"
_META_GLOB = "META_TEST_*.md"


def _handoff_key(p: Path) -> tuple[str, float]:
    """Order dated handoffs by the ISO date in the name, then mtime to break same-day ties (a plain
    filename sort orders same-day handoffs by slug - the truly-latest could lose to an alphabetically
    later earlier one). Newest sorts LAST, so the latest dated handoff is ``[-1]``."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
    return (m.group(1) if m else "", p.stat().st_mtime)


def self_substrate(repo_root: Path | str) -> dict[str, list[str]]:
    """The self-nodes within the conceptric, by role - the one definition of "what is the self".

    Discovered from the directory's membership (the same tree the shard covers), existence-filtered
    so a deleted file drops out (the self degrades through the graph, it does not crash).
    ``handoffs`` is newest-LAST, so the latest dated handoff is ``handoffs[-1]``."""
    repo_root = Path(repo_root)

    def _existing(names: list[str]) -> list[str]:
        return [n for n in names if (repo_root / n).is_file()]

    handoffs = sorted((p for p in repo_root.glob(_HANDOFF_GLOB) if p.is_file()), key=_handoff_key)
    meta = sorted(p for p in repo_root.glob(_META_GLOB) if p.is_file())
    return {
        "fixed_point": _existing(_SELF_ROLES["fixed_point"]),
        "map": _existing(_SELF_ROLES["map"]),
        "protocol": _existing(_SELF_ROLES["protocol"]),
        "guides": _existing(_SELF_ROLES["guides"]),
        "handoffs": [_rel(repo_root, p) for p in handoffs],
        "meta": [_rel(repo_root, p) for p in meta],
    }


def read_source(repo_root: Path | str, name: str) -> str:
    """The one sealed reader: re-read a node's full source through the conceptric.

    Both the self's graded reconstruction (``self_corpus.reconstruct_self``, the hello) and orient's
    self-knowledge routing (``canon._route_self_knowledge``) read self-substrate content through THIS
    function - one reader, not two raw file reads that can diverge (N21). The soul covenant holds: a
    soul node yields ``""`` (never content, at any grade). Missing / binary -> ``""`` (never a hard
    dependency). Full text, uncapped - the caller carves the slice it needs."""
    repo_root = Path(repo_root)
    rel = name.replace("\\", "/")
    if _is_soul(rel):
        return ""
    path = repo_root / rel
    if path.suffix.lower() not in _TEXT_EXT or not path.is_file():
        return ""
    return _read_text(path)


def default_repo_root() -> Path:
    """The engine's own repo root - ``src/laplace/engine/self_shard.py`` -> ``parents[2]``."""
    return source_tree()


def main(argv: list[str]) -> int:
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    cmd = argv[0] if argv else "build"
    repo_root = default_repo_root()
    grade = 0
    for a in argv:
        if a.startswith("--grade="):
            grade = int(a.split("=", 1)[1])

    if cmd == "build":
        shards = shard_repo(repo_root)
        path = write_index(repo_root, shards)
        rep = shard_faithfulness(repo_root, shards)
        print(f"sharded {len(shards)} objects -> {path.name}")
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0 if rep["pass"] else 1
    if cmd == "name":
        query = " ".join(a for a in argv[1:] if not a.startswith("--"))
        print(json.dumps(reconstruct_by_name(repo_root, query, grade=grade),
                         ensure_ascii=False, indent=2))
        return 0
    if cmd == "verify":
        rep = shard_faithfulness(repo_root)
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0 if rep["pass"] else 1
    print("usage: self_shard [build|name <query> [--grade=k]|verify]")
    return 2


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))


# ---- moved from laplace.web.scanner (2026-10-21, core native/physical closure)
def _shard_group(name: str, kind: str, sealed: bool) -> str:
    """The self layer for a file: its directory, two segments deep where that helps.

    Soul is its own sealed layer; repo-root files are 'root'. Two-segment grouping
    splits a big project dir (paper_operatorial_loss/inputs vs /manuscript vs
    /numerics) into readable layers instead of one 200-node blob - the readability
    pass: no single layer should be a hairball when opened.
    """
    if sealed:
        return "soul"
    parts = name.split("/")
    if len(parts) == 1:
        return "root"          # repo-root files (HANDOFF.md, the dated handoffs, ...)
    if len(parts) >= 3:
        return parts[0] + "/" + parts[1]   # dir/subdir, so a project splits by area
    return parts[0]


def self_graph(root=None) -> dict:
    """The directory shard as the one node/edge model - the engine's own tree.

    Every tracked file is a ``file:<relpath>`` node carrying its grade-0 handle
    (essence + keywords); edges are the shard's inter-object wiring (imports /
    links / inputs) resolved to file ids. Soul nodes carry a sealed handle only.

    ``root`` defaults to the engine repo (what the live lens serves); the conceptric
    dreamer passes an explicit root so it reshapes - and is tested on - any tree.
    """
    from laplace.engine import self_shard

    root = Path(root) if root is not None else _repo_root()
    shards = self_shard.shard_repo(root)

    # Resolver: a shard edge ``to`` -> a file node id, best-effort, never faked.
    names = set(shards)
    by_base: dict[str, list[str]] = {}
    for n in names:
        by_base.setdefault(n.rsplit("/", 1)[-1], []).append(n)

    def _resolve(kind: str, to: str) -> str | None:
        to = to.strip()
        if not to:
            return None
        if kind == "import":  # laplace.X.Y -> src/laplace/X/Y.py, or the package's __init__.py
            module = to.replace(".", "/")
            for cand in (f"src/laplace/{module}.py", f"src/laplace/{module}/__init__.py"):
                if cand in names:
                    return cand
            return None
        if to in names:  # exact relpath (md links, tex inputs)
            return to
        for suf in (".md", ".tex", ".py"):  # input/link without suffix
            if to + suf in names:
                return to + suf
        base = to.rsplit("/", 1)[-1]
        hits = by_base.get(base) or by_base.get(base + ".md") or []
        return hits[0] if len(hits) == 1 else None

    nodes = []
    for name, sh in shards.items():
        lines = sh.get("lines", 0) or 0
        # weight 0..1 by log-size, so a big module renders larger than a stub.
        weight = min(1.0, 0.25 + (lines ** 0.5) / 40.0) if lines else 0.25
        nodes.append({
            "id": f"file:{name}", "kind": "soul" if sh["sealed"] else (sh.get("kind") or "file"),
            "label": name.rsplit("/", 1)[-1], "group": _shard_group(name, sh.get("kind", ""), sh["sealed"]),
            "status": None, "weight": round(weight, 3), "source": "self", "link": "linked",
            "meta": {"path": name, "essence": sh["essence"], "keywords": sh.get("keywords", []),
                     "lines": lines, "sealed": sh["sealed"], "kind": sh.get("kind", "")},
        })
    edges = []
    seen: set[tuple] = set()
    for name, sh in shards.items():
        src = f"file:{name}"
        for e in sh.get("edges", []):
            dst_name = _resolve(e.get("kind", ""), e.get("to", ""))
            if not dst_name or dst_name == name:
                continue
            dst = f"file:{dst_name}"
            key = (src, dst, e.get("kind", ""))
            if key in seen:
                continue
            seen.add(key)
            edges.append({"src": src, "dst": dst, "rel": e.get("kind", "link"),
                          "evidence": "", "source": "self", "count": 1})
    return {"nodes": nodes, "edges": edges, "source": "self",
            "health": {"node_count": len(nodes), "edge_count": len(edges),
                       "sealed": sum(1 for s in shards.values() if s["sealed"])}}
