"""The manuscript<->conceptric bridge for the feedback editor.

The editor (served by ``scanner.py`` at ``/editor``) shows the compiled PDF in one
panel and the *project conceptric* in the other: the source files a manuscript is
projected from, parsed into addressable nodes. Feedback the author leaves on the PDF
binds to one of those nodes and is deposited as TYPED FRICTION -- never a patch to the
``.tex``. Re-projection regrows the bound node and regenerates its section.

This is the loop made operable: comment -> friction on a node -> re-project. The bridge
owns three things only -- where a project lives, how its source files atomise into
nodes, and the feedback ledger. The generation itself stays in the projection skills.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

from laplace.pipeline.ledger import append_jsonl as _append_jsonl

# The eight source files a self-theory-shaped project is projected from, GRADED into
# the three bands the projection descends through: the narrative spine at the apex
# (the manuscript's skeleton), the results it derives, and the external substrate it
# rests on. Projecting = adding prose flesh to this skeleton, so the editor renders it
# top-down. (grade, role) per file; a project may override this manifest later.
_LAYERS = {
    "BLUEPRINT.md":     (0, "guide"),       # the apex: the artefact-agnostic top-level guide —
    "SPINE.md":         (0, "guide"),       #   what this IS + the argument through-line. Any
    "FOUNDATION.md":    (1, "results"),     #   artefact (manuscript, talk) projects FROM here.
    "PROOF.md":         (1, "results"),     # what the program derives
    "CLAIMS_LEDGER.md": (1, "results"),
    "GROUND.md":        (2, "substrate"),   # the external floor it stands on (+ numerics)
    "TERMS.md":         (2, "substrate"),
    "REFERENCES.md":    (2, "substrate"),
}
_SOURCE_FILES = list(_LAYERS)
_ROLE_ORDER = ["guide", "results", "substrate", "references"]

# The numerics are first-class conceptric nodes, not "parts of the manuscript": each demo is a
# node in the substrate carrying its OWN viewable artefacts (figure, script slice, measured
# result) and evidencing a named result above it. An artefact (PDF, talk) may or may not render
# them; the conceptric holds them regardless. (key -> the result-token each demo tests.)
_NUMERIC_EVIDENCE = {"metriplectic": "Lemma 3", "descent": "C7", "dilation": "T1", "margin": "T3"}
_NUMERIC_LABEL = {"metriplectic": "The metriplectic split (Fig.)", "descent": "Strict descent (Fig.)",
                  "dilation": "The minimal unitary dilation (Fig.)", "margin": "The margin / fixed point (Fig.)"}

# A node carries a coupling TOKEN if its label names a referable result: a claim Cn, a
# theorem Tn, a lemma, an external ground Gn / G-Ham, an assumption An, a named result
# R_x. Any other node whose BODY mentions that token draws an edge to it — that is how
# the spine's "each beat ⋈ what it derives" surfaces mechanically, no hand-wiring.
_TOKEN_PATS = [
    re.compile(r"^(C\d+)\b"),
    re.compile(r"^(?:Theorem\s+)?(T\d+)\b"),
    re.compile(r"^(Lemma\s+\d+)\b"),
    re.compile(r"^(G(?:\d+|-Ham|-?Ham))\b"),
    re.compile(r"^(A\d+)['′]?\b"),
    re.compile(r"^(R_\w+|R\d+)\b"),
]


def _token_of(label: str) -> str | None:
    for pat in _TOKEN_PATS:
        m = pat.match(label.strip())
        if m:
            return m.group(1)
    return None

# A conceptric node opens at a heading or at a bolded marker bullet. Each pattern
# captures the label; the body runs to the next marker. Order matters only for which
# label a line reports -- the line set is a partition.
_MARKERS = [
    ("heading", re.compile(r"^(#{1,4})\s+(.*\S)\s*$")),
    ("claim",   re.compile(r"^\s*[-*]\s+\*\*(C\d+[^*]*)\*\*\s*(.*)$")),
    ("assume",  re.compile(r"^\s*[-*]\s+\*\*\((A\d+[^)]*)\)\*\*\s*(.*)$")),
    ("ground",  re.compile(r"^\s*\*\*(G[\w-]+\s*[—-][^*]*)\*\*\s*(.*)$")),
]

_MAXBODY = 4000  # cap a node body so the panel payload stays bounded


def project_root(repo: Path, project: str) -> Path:
    return repo / project


def _node_id(file_stem: str, label: str) -> str:
    # a stable, URL-safe id: FILE#slug. A marker label (C5, T1, A2, G1) is one token and
    # stays short; a heading slugs its first few words so headings stay distinct. Collisions
    # are broken by the line anchor in _atomise.
    toks = re.findall(r"[\w]+", label)
    slug = "-".join(toks[:5]) or "sec"
    return f"{file_stem}#{slug}"


def _atomise(path: Path) -> list[dict]:
    """Split one source file into conceptric nodes at headings and marker bullets."""
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    marks: list[tuple[int, str, str]] = []  # (line_idx, kind, label)
    for i, ln in enumerate(lines):
        for kind, pat in _MARKERS:
            m = pat.match(ln)
            if m:
                label = (m.group(2) if kind == "heading" else m.group(1)).strip()
                marks.append((i, kind, label))
                break
    nodes: list[dict] = []
    stem = path.stem
    seen: set[str] = set()
    for j, (line_idx, kind, label) in enumerate(marks):
        end = marks[j + 1][0] if j + 1 < len(marks) else len(lines)
        body = "\n".join(lines[line_idx:end]).strip()[:_MAXBODY]
        nid = _node_id(stem, label)
        if nid in seen:                       # break a collision with the line anchor
            nid = f"{nid}-L{line_idx + 1}"
        seen.add(nid)
        grade, role = _LAYERS.get(path.name, (1, "results"))
        nodes.append({
            "id": nid,
            "file": path.name,
            "kind": kind,
            "label": label,
            "anchor": line_idx + 1,        # 1-based line for "open the source here"
            "body": body,
            "grade": grade,
            "role": role,
            "token": _token_of(label),     # the referable handle, if any
        })
    return nodes


def _couple(nodes: list[dict]) -> list[dict]:
    """Derive coupling edges: a node whose body names another node's token draws from it.

    This is how the apex spine's "each beat ⋈ what it derives" surfaces with no hand-wiring
    — the same descent the projection rides, read off the source itself."""
    by_token = {n["token"]: n["id"] for n in nodes if n.get("token")}
    if not by_token:
        return []
    # one alternation over all tokens; longest first so 'Lemma 3' wins over a bare 'T3'
    toks = sorted(by_token, key=len, reverse=True)
    rx = re.compile(r"\b(" + "|".join(re.escape(t) for t in toks) + r")\b")
    edges, seen = [], set()
    for n in nodes:
        # skip the node's own header line so a node never couples to itself by its title
        body = "\n".join(n["body"].splitlines()[1:])
        for m in rx.finditer(body):
            dst = by_token[m.group(1)]
            if dst == n["id"]:
                continue
            key = (n["id"], dst)
            if key in seen:
                continue
            seen.add(key)
            edges.append({"src": n["id"], "dst": dst, "via": m.group(1)})
    return edges


def project_numerics(repo: Path, project: str) -> list[dict]:
    """The numeric demonstrations as conceptric nodes, each carrying its viewable artefacts."""
    fpy = project_root(repo, project) / "manuscript" / "figures" / "make_figures.py"
    if not fpy.is_file():
        return []
    lines = fpy.read_text(encoding="utf-8").splitlines()
    defs = [(i, m.group(1)) for i, ln in enumerate(lines)
            if (m := re.match(r"def fig_(\w+)\(", ln))]
    nodes = []
    for j, (start, key) in enumerate(defs):
        end = defs[j + 1][0] if j + 1 < len(defs) else len(lines)
        src = "\n".join(lines[start:end]).strip()
        measured = " ".join(ln.strip() for ln in lines[start:end] if "print(" in ln)
        nodes.append({
            "id": f"NUMERIC#{key}", "file": "make_figures.py", "kind": "numeric",
            "label": _NUMERIC_LABEL.get(key, key), "anchor": start + 1,
            "grade": 2, "role": "substrate", "token": f"fig:{key}",
            "body": src[:_MAXBODY],
            "artefacts": {
                "figure": f"figures/fig_{key}.pdf",
                "script": {"file": "manuscript/figures/make_figures.py",
                           "start": start + 1, "end": end, "source": src[:_MAXBODY]},
                "measured": measured,
            },
            "evidences": _NUMERIC_EVIDENCE.get(key),
        })
    return nodes


_SECTION_ROW = re.compile(r"^\|\s*\*\*(\d+)\.\s*([^*|]+?)\*\*\s*\|(.*)\|(.*)\|(.*)\|\s*$")


def artefact_provenance(repo: Path, project: str) -> dict:
    """The artefact, linearly read, each part wired to what informed it.

    Parses SPINE.md's authored '§ ⋈ what it derives ⋈ grounded-in' form table: the design-time
    provenance map. Each section resolves its derive-tokens to conceptric node ids, so selecting a
    part of the manuscript brings out exactly the nodes that fed it — the inversion of scrolling a
    flat list. Artefact-agnostic in shape; today the artefact is the manuscript."""
    root = project_root(repo, project)
    concept = project_conceptric(repo, project)
    by_token = {n["token"]: n for g in concept["groups"] for n in g["nodes"] if n.get("token")}
    spine = (root / "SPINE.md")
    sections = []
    if spine.is_file():
        for ln in spine.read_text(encoding="utf-8").splitlines():
            m = _SECTION_ROW.match(ln)
            if not m:
                continue
            num, title = m.group(1), m.group(2).strip()
            beat, derives, grounded = m.group(3), m.group(4), m.group(5)
            toks = []
            for pat in _TOKEN_PATS:
                inline = re.compile(pat.pattern.lstrip("^"))   # patterns are start-anchored; scan inline
                toks += inline.findall(derives)
            seen, informed = set(), []
            for t in toks:
                node = by_token.get(t)
                if node and node["id"] not in seen:
                    seen.add(node["id"])
                    informed.append({"id": node["id"], "token": t, "label": node["label"],
                                     "grade": node["grade"], "role": node["role"]})
            numerics = []
            if re.search(r"numeric", derives, re.I):
                numerics = [{"id": n["id"], "label": n["label"]} for g in concept["groups"]
                            for n in g["nodes"] if n["kind"] == "numeric"]
            sections.append({
                "num": int(num), "title": title,
                "beat": re.sub(r"\s+", " ", beat).strip().lstrip("*").strip(),
                "informed_by": informed,
                "grounded_in": re.sub(r"\s+", " ", grounded).strip(),
                "numerics": numerics,
            })
    return {"project": project, "artefact": "manuscript", "n_sections": len(sections),
            "sections": sections}


_BIB_ENTRY = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)(?=\n@|\Z)", re.DOTALL)


def _bibfield(body: str, name: str) -> str:
    m = re.search(name + r"\s*=\s*\{(.*?)\}\s*[,}\n]", body, re.DOTALL | re.IGNORECASE)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def project_references(repo: Path, project: str) -> list[dict]:
    """The manuscript's bibliography as substrate LEAF nodes — the broadest, most numerous layer.
    Each cited work is a node (token = citekey), so any source/result that names the key couples
    down to it and the manuscript's citations link directly into the substrate floor."""
    bib = project_root(repo, project) / "manuscript" / "refs.bib"
    if not bib.is_file():
        return []
    text = bib.read_text(encoding="utf-8")
    nodes = []
    for m in _BIB_ENTRY.finditer(text):
        key, body = m.group(2), m.group(3)
        author = _bibfield(body, "author"); title = _bibfield(body, "title")
        year = _bibfield(body, "year")
        first = author.split(" and ")[0].split(",")[0].strip() if author else "?"
        nodes.append({
            "id": f"REF#{key}", "file": "refs.bib", "kind": "reference",
            "label": f"{first} {year}".strip(), "anchor": 0, "grade": 3, "role": "references",
            "token": key, "body": (title + (f"\n{author}" if author else "")).strip()[:_MAXBODY],
        })
    return nodes


def project_conceptric(repo: Path, project: str) -> dict:
    """The GRADED, artefact-agnostic project conceptric: source nodes banded guide->substrate
    ->references (numerics + the bibliography first-class), plus the coupling edges between them.
    The tree the manuscript projects from: narrow narrative apex, broad reference base."""
    root = project_root(repo, project)
    groups, all_nodes = [], []
    for fname in _SOURCE_FILES:
        nodes = _atomise(root / fname)
        if not nodes:
            continue
        all_nodes.extend(nodes)
        grade, role = _LAYERS[fname]
        groups.append({"file": fname, "grade": grade, "role": role,
                       "count": len(nodes), "nodes": nodes})
    nums = project_numerics(repo, project)
    if nums:
        all_nodes.extend(nums)
        groups.append({"file": "make_figures.py · numerics", "grade": 2, "role": "substrate",
                       "count": len(nums), "nodes": nums})
    refs = project_references(repo, project)
    if refs:
        all_nodes.extend(refs)
        groups.append({"file": "refs.bib · bibliography", "grade": 3, "role": "references",
                       "count": len(refs), "nodes": refs})
    edges = _couple(all_nodes)
    # explicit evidence edges: each numeric -> the result it tests (numeric draws-from result)
    by_token = {n["token"]: n["id"] for n in all_nodes if n.get("token")}
    for n in nums:
        ev = n.get("evidences")
        if ev and ev in by_token and by_token[ev] != n["id"]:
            edges.append({"src": n["id"], "dst": by_token[ev], "via": "evidences"})
    # band the groups by role for top-down rendering
    bands = []
    for role in _ROLE_ORDER:
        members = [g for g in groups if g["role"] == role]
        if members:
            bands.append({"role": role, "grade": members[0]["grade"],
                          "files": members, "n": sum(g["count"] for g in members)})
    return {"project": project, "n_nodes": len(all_nodes), "n_files": len(groups),
            "n_edges": len(edges), "groups": groups, "bands": bands, "edges": edges}


# --------------------------------------------------------------------------- feedback

def _feedback_path(repo: Path, project: str) -> Path:
    d = project_root(repo, project) / "feedback"
    d.mkdir(parents=True, exist_ok=True)
    return d / "feedback.jsonl"


def feedback_list(repo: Path, project: str, ledger: Path | None = None) -> dict:
    """List the ledger. ``ledger`` overrides the project-registry path so other
    surfaces (the projection viewer's review mode) reuse the one mechanism."""
    path = ledger if ledger is not None else _feedback_path(repo, project)
    records = []
    if path.is_file():
        for ln in path.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln:
                try:
                    row=json.loads(ln)
                    if row.get('record')!='feedback-origin-settlement':records.append(row)
                except ValueError:
                    pass
    records.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return {"project": project, "n": len(records), "open": sum(
        1 for r in records if r.get("status") == "open"), "records": records}


def feedback_add(repo: Path, project: str, payload: dict,
                 ledger: Path | None = None, *, origin: dict | None = None) -> dict:
    """Deposit one typed-friction record against a conceptric node. Append-only.
    ``ledger`` overrides the project-registry path (projection-viewer reuse)."""
    node_id = (payload.get("node_id") or "").strip()
    comment = (payload.get("comment") or "").strip()
    if not node_id or not comment:
        return {"error": "node_id and comment are required"}
    from laplace.work.feedback import validate_feedback
    try:
        target, effect = validate_feedback(project, payload, repo)
    except ValueError as exc:
        return {"error": str(exc)}
    if target:
        payload = {**payload, "anchor": {**(payload.get("anchor") if isinstance(payload.get("anchor"),dict) else {}),
                   "feedback_target": target, "feedback_effect": effect,
                   "context_role": "observation-only" if effect == "observation_only" else (payload.get("anchor") if isinstance(payload.get("anchor"),dict) else {}).get("context_role")}}
    rec = {
        "id": _dt.datetime.now().strftime("FB-%Y%m%d-%H%M%S-") + node_id.split("#")[-1],
        "project": project,
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "node_id": node_id,
        "node_label": payload.get("node_label", ""),
        "kind": payload.get("kind", "note"),          # missing-derivation|imprecise|refute|off-voice|note
        "anchor": payload.get("anchor", {}),           # {page, quote, section}
        "comment": comment,
        # THE ACTOR LAW (W-HANDS): his name is never a silent default — the
        # Python door's fallback names the engine itself (mirrors friction_add's
        # by=payload.get("by", "eigen")); callers that know their actor (the
        # HTTP door, growth_surface, review_surface) pass it explicitly.
        "by": payload.get("by", "eigen"),
        "status": "open",
    }
    if origin is not None:
        # Created only by the authoring owner; public payload fields cannot
        # supply retained request authority or invent an AC alias.
        rec['authoring_origin']=dict(origin)
    if payload.get("re"):                 # a REPLY: threads under its parent record
        rec["re"] = str(payload["re"])
    # THE ALTITUDE FIELDS (the redline composer): ``scope`` is the row's altitude
    # (``schema.FEEDBACK_SCOPES`` — the six already typed in his own ledger rows),
    # ``scope_source`` says whether he chose it or a rule inferred it, and
    # ``suggested_scope`` records what the rule leaned toward. All three are
    # OPTIONAL and each is written ONLY when the caller supplies it: a payload that
    # names none mints exactly the record shape every existing caller already gets
    # (absent scope = unscoped, a first-class state). Validation lives at the door
    # that takes the author's gesture (``review_surface.adjudicate``); this writer
    # persists what it is given, refusing a value outside the vocabulary rather
    # than silently banking a scope no consumer can group by.
    from laplace.pipeline import schema as _schema
    for field, roster in (("scope", _schema.FEEDBACK_SCOPES),
                          ("suggested_scope", _schema.FEEDBACK_SCOPES),
                          ("scope_source", _schema.SCOPE_SOURCES)):
        val = (payload.get(field) or "").strip() if isinstance(
            payload.get(field), str) else payload.get(field)
        if not val:
            continue
        if val not in roster:
            return {"error": f"{field} must be one of {list(roster)}; got {val!r}"}
        rec[field] = val
    # the composition fold: a posted record carrying a composed block keeps it when the
    # block is schema-clean; an invalid block refuses in plain words; an absent block mints
    # nothing (unchanged behaviour — total backward compat for every caller that posts no
    # composed field). The block is authored by the writer that held the integration
    # context, so the ledger keeps it whole rather than synthesising a glance at read time.
    block = payload.get("composed")
    if block is not None:
        from laplace.pipeline import composed as _composed
        try:
            _composed.validate_composed(block)
        except ValueError as e:
            return {"error": f"composed block refused: {e}"}
        rec["composed"] = block
    path = ledger if ledger is not None else _feedback_path(repo, project)
    if payload.get("supersedes"):
        prior = str(payload["supersedes"])
        if not any(row.get("id") == prior for row in feedback_list(repo, project, ledger=path)["records"]):
            return {"error": "the feedback record to supersede is not in this project ledger"}
        rec["supersedes"] = prior
    guard=None
    if origin is not None:
        from laplace.pipeline import correction_origin
        required=path.is_file()
        def guard():
            found=correction_origin.locked_outcome(repo,project,path,origin['request_id'],
                intent=origin['intent_sha256'],required=required)
            return {'origin_outcome':found} if found else None
    outcome=append_feedback_record(path, rec,origin_guard=guard)
    if outcome:return {'ok':True,**outcome}
    return {"ok": True, "record": rec}


def append_feedback_record(path: Path, record: dict, *, origin_guard=None) -> dict | None:
    """Mint and append under the existing one ledger lock, preserving old IDs."""
    candidate = record['id']
    def mint():
        if origin_guard is not None:
            outcome=origin_guard()
            if outcome:return outcome
        record['id'] = _unique_feedback_id(path, candidate)
        return None
    return _append_jsonl(path, record, precondition=mint)


def _unique_feedback_id(path: Path, candidate: str) -> str:
    """A row id that names EXACTLY ONE row.

    The id is minted ``FB-<date>-<HHMMSS>-<node tail>``, which is unique only while no two
    deposits land on the same node inside the same second. The redline walk's whole premise
    is that depositing costs nothing, so that is not an edge case there: a measured sweep
    banked eight rows against one section in one second and every one of them read back
    under the same id — which silently breaks the doors that TARGET a row by id (confirm,
    defer, revoke, the walk's undo) and breaks the echo law, whose receipt is the row id.

    So a colliding id takes an ordinal suffix (``…-front-2``, ``-3``, …). The first row of
    any second keeps the historical shape exactly, so nothing already banked moves and no
    reader that matches on the old format sees a change."""
    if not path.is_file():
        return candidate
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raise                                 # unreadable IDs cannot justify uniqueness
    used = set(re.findall(r'"id"\s*:\s*"([^"\\]*)"', raw))
    if candidate not in used:
        return candidate
    n = 2
    while f"{candidate}-{n}" in used:
        n += 1
    return f"{candidate}-{n}"


#: the author's own actor name(s) — the identity a remote (public, unauthenticated)
#: channel must never be able to assume or impersonate. Checked case/space-insensitively.
AUTHOR_ACTORS = frozenset({"gerard"})

#: the author's remote handle — the username-as-key (his ruling, 2026-07-11 docket
#: session: "the unlock on feedback worth a damn is through username not passphrase").
#: A remote record whose visitor name matches is re-minted ``author-claimed:<handle>``
#: so his editor queue can route it author-tier — but it is NEVER minted ``gerard``:
#: a public handle is claimable by anyone who knows it, and the ledger keeps that
#: epistemic distinction. The handle lives only in this private repo; the public demo
#: bundle treats every name identically, so the source leaks nothing.
AUTHOR_CLAIM_HANDLES = frozenset({"phujck"})


def feedback_ingest(repo: Path, project: str, record: dict,
                    ledger: Path | None = None, channel: str = "local") -> dict:
    """Fold a record minted ELSEWHERE (a remote review device) into the ledger,
    PRESERVING its id and ts so a comment is the same object wherever it was born.

    The write-side twin of ``feedback_add`` (which mints fresh): the drain
    (``scripts/drain_feedback.py``) hands each inbox record here. Revalidates the
    load-bearing fields, dedups by id (idempotent re-drain), and appends through the
    ONE ledger mechanism — never a hand-edit of the jsonl. Returns
    ``{ok, id}`` on append, ``{skipped, id}`` on a dup, ``{error}`` on a bad record.

    ``channel`` distinguishes the author's own local flow (``"local"``, the default —
    today's law, unchanged: ``by`` defaults to ``"gerard"``) from the public demo's
    remote genre (``"remote"`` — a stranger's browser via the drain). The actor guard,
    remote only (mirrors ``review_surface.adjudicate``'s: the door defaults nowhere):
    ``by`` must be present and must start with ``"visitor:"`` plus a non-empty name,
    and must not (case/space-insensitively) name an author actor in ``AUTHOR_ACTORS``
    — a record with no actor, or one claiming to BE the author, is refused before any
    append, so the author can never be impersonated through the remote channel."""
    if channel == "remote":
        by_raw = (record.get("by") or "").strip()
        if not by_raw:
            return {"error": "remote feedback requires an explicit visitor actor "
                              "(by): this channel defaults nowhere"}
        if by_raw.strip().lower() in AUTHOR_ACTORS:
            return {"error": "remote feedback may not claim an author actor"}
        if not by_raw.startswith("visitor:") or not by_raw[len("visitor:"):].strip():
            return {"error": "remote feedback's by must be visitor:<name>"}
        name = by_raw[len("visitor:"):].strip()
        if name.lower() in AUTHOR_CLAIM_HANDLES:
            by_raw = f"author-claimed:{name.lower()}"
    node_id = (record.get("node_id") or "").strip()
    comment = (record.get("comment") or "").strip()
    fb_id = (record.get("id") or "").strip()
    if not node_id or not comment or not fb_id:
        return {"error": "id, node_id and comment are required"}
    path = ledger if ledger is not None else _feedback_path(repo, project)
    existing = {r.get("id") for r in feedback_list(repo, project, ledger=path)["records"]}
    if fb_id in existing:
        return {"skipped": True, "id": fb_id}
    rec = {
        "id": fb_id,
        "project": record.get("project", project),
        "ts": record.get("ts") or _dt.datetime.now().isoformat(timespec="seconds"),
        "node_id": node_id,
        "node_label": record.get("node_label", ""),
        "kind": record.get("kind", "note"),
        "anchor": record.get("anchor", {}),
        "comment": comment,
        "by": record.get("by", "gerard") if channel != "remote" else by_raw,
        "status": record.get("status", "open"),
    }
    _append_jsonl(path, rec)                # the ONE locked append (write-side twin of feedback_add)
    return {"ok": True, "id": fb_id}


def feedback_resolve(repo: Path, project: str, fb_id: str, status: str = "resolved",
                     ledger: Path | None = None, *, note: str = "", by: str = "author",
                     expected_status: str | None = None, applied_record_id: str | None = None) -> dict:
    """Update one status atomically; optional owner settlement guards its prior state."""
    if status not in {"open", "resolved", "dismissed"}:
        return {"error": "feedback status must be open, resolved, or dismissed"}
    note = str(note or "").strip()
    if len(note.encode("utf-8")) > 20_000:
        return {"error": "feedback status note is too large"}
    if expected_status is not None and expected_status not in {"open","resolved","dismissed"}:
        return {"error":"expected feedback status is unsupported"}
    if applied_record_id is not None and (not isinstance(applied_record_id,str) or not applied_record_id):
        return {"error":"applied feedback record ID must be a nonempty string"}
    path = ledger if ledger is not None else _feedback_path(repo, project)
    if not path.is_file():
        return {"error": "no feedback ledger"}
    from filelock import FileLock
    with FileLock(str(path) + ".lock", timeout=10):
        out, hit, changed, selected = [], False, False, None
        records=[json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        matching=[record for record in records if record.get("id")==fb_id]
        if expected_status is not None and (len(matching)!=1 or matching[0].get("status","open")!=expected_status):
            return {"error":"feedback status changed or ID is ambiguous; owner settlement was not applied","ok":False}
        for rec in records:
            if rec.get("id") == fb_id:
                hit = True
                previous = rec.get("status", "open")
                if previous != status or note:
                    event = {"status": status, "at": _dt.datetime.now().isoformat(timespec="seconds"),
                             "by": str(by or "author")}
                    if note:
                        event["note"] = note
                    if applied_record_id is not None:
                        event["applied_record_id"] = applied_record_id
                    rec["status_history"] = list(rec.get("status_history") or []) + [event]
                    rec["status"] = status
                    if note:
                        rec["status_note"] = note
                    else:
                        rec.pop("status_note", None)
                    changed = True
                selected = dict(rec)
            out.append(rec)
        if changed:
            pending = path.with_name(path.name + ".status.pending")
            pending.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n",
                               encoding="utf-8")
            pending.replace(path)
    return {"ok": hit, "changed": changed, "id": fb_id, "status": status,
            "record": selected}


# --------------------------------------------------------------- the findings consumer
# The machine-finding consumer (W-CONSUMER, 2026-07-22). The per-project feedback ledger
# is where the mechanical panel / readers / holdout pour their DETECTIONS (source
# ``mech-panel:<round>`` / ``reader`` / ``R7`` / ``holdout-…`` / ``machine``). The desk
# EXCLUDES these from the author's queue (his to rule are the author-sourced ones), and
# nothing else retired them — so panel round on panel round accumulated, unretired, into
# the machine-finding backlog the census found. `ledger.live_findings` already hides the
# prior rounds from every WORKLIST view (only the latest panel round is live), but the raw
# ledger keeps them forever, `status: "open"`. This consumer makes that round-supersession
# an EXPLICIT, append-only ledger fact: a regenerated fragment for a section CONSUMES the
# prior-round machine findings anchored to it (their subject — the bytes they were raised
# on — is gone), each retired with a `consumed_by {round, packet}` resolution. A defect
# that survives regeneration is re-found FRESH by the next panel round (a new record, new
# id, new content fingerprint), so retirement never hides a live defect.


def _non_finding_records() -> frozenset:
    """Feedback ``record`` types that are ACTIONS on a finding (adjudications /
    suppressions / author edits / the txn journal), never findings themselves. Built from
    the SAME canonical constants desk._NON_FINDING_RECORDS / review_surface use, so the
    consumer's "is this a finding" agrees with the desk and review readers."""
    from laplace.pipeline import adjudicate as _adj
    from laplace.pipeline import suppress as _sup
    from laplace.pipeline import edits as _ed
    return frozenset(_adj.ADJ_RECORD_KINDS
                     | {_sup.RECORD_KIND, _sup.REVOKE_KIND, _ed.RECORD_KIND, "txn"})


def _is_author_sourced(rec: dict) -> bool:
    """True when a feedback record is AUTHOR-origin (his to adjudicate on the desk),
    NOT a machine detection. Mirrors desk._is_author_sourced exactly (the annotate door
    stamps an author ``by``; the relay path stamps an ``author…`` / source-doc
    ``source``); a machine panel stamps neither."""
    by = (rec.get("by") or "").strip().lower()
    src = (rec.get("source") or "").strip().lower()
    if by in AUTHOR_ACTORS or by.startswith("author") or by.startswith("visitor:"):
        return True
    return (src.startswith("the-author") or src.startswith("author")
            or "feedback/sources/" in src)


def is_machine_finding(rec: dict) -> bool:
    """A MACHINE-detected feedback finding: a real, open detection (panel / reader /
    holdout), not an action-on-a-finding record and not author-sourced. The class the
    desk excludes and nothing retired — the consumer's exact subject."""
    if not isinstance(rec, dict):
        return False
    if rec.get("record") in _non_finding_records():
        return False
    return not _is_author_sourced(rec)


def _finding_section(rec: dict) -> str:
    return str(rec.get("section") or (rec.get("anchor") or {}).get("section") or "").strip()


def finding_round(rec: dict, panel_prefix: str = "mech-panel:") -> int | None:
    """The panel round a finding was minted in — from its ``source: mech-panel:<N>``
    (the same parse ``ledger.live_findings`` rounds by), else ``provenance.round`` /
    ``round``. ``None`` for a round-less finding (a legacy pour, or a non-panel reader):
    treated as predating any numbered round when the land-side asks 'is this prior?'."""
    src = str(rec.get("source") or "")
    if src.startswith(panel_prefix):
        digits = ""
        for ch in src[len(panel_prefix):]:
            if ch.isdigit():
                digits += ch
            elif digits:
                break
        if digits:
            return int(digits)
    for cand in (rec.get("round"), (rec.get("provenance") or {}).get("round")):
        try:
            if cand is not None:
                return int(cand)
        except (TypeError, ValueError):
            pass
    return None


def machine_findings_for_section(records: list, section: str, *,
                                 before_round: int | None = None) -> list[dict]:
    """The OPEN machine findings anchored to ``section``, LIVE (a later ``supersedes``
    retires one — ``adjudicate.live`` semantics, so an already-consumed finding is gone).
    ``before_round``: keep only findings minted in a round STRICTLY BEFORE it — the
    current round's fresh re-mint is never consumed. ``None`` keeps every round (the
    ATTACH view: the section's whole open backlog, most-recent first)."""
    from laplace.pipeline import adjudicate as _adj
    sec = str(section or "").strip()
    out: list[dict] = []
    for r in _adj.live(records):
        if not is_machine_finding(r):
            continue
        if (r.get("status") or "open") != "open":
            continue
        if _finding_section(r) != sec:
            continue
        if before_round is not None:
            fr = finding_round(r)
            if fr is not None and fr >= before_round:
                continue
        out.append(r)
    out.sort(key=lambda r: str(r.get("ts") or ""), reverse=True)
    return out


def feedback_consume(repo: Path | None, project: str, finding: dict, *,
                     round: int, packet: str, actor: str = "findings-consumer",
                     ledger: Path | None = None) -> dict:
    """The retire / consumed-by append (the consumer's write half). Retire ONE machine
    finding as CONSUMED by a regenerated fragment: an append-only superseding resolution
    row (reusing ``adjudicate.make_resolution`` — the finding-retire maker) carrying a
    ``consumed_by {round, packet}`` block. NOT ``feedback_resolve`` (that mutates a past
    line's status in place — this keeps the ledger append-only, so the retirement reads as
    history: the resolution names the round and packet whose regeneration superseded the
    finding's subject). A finding with no id is unaddressable and refused (nothing to
    supersede)."""
    from laplace.pipeline import adjudicate as _adj
    fid = str(finding.get("id") or "").strip()
    if not fid:
        return {"error": "finding has no id — unaddressable, cannot retire"}
    sec = _finding_section(finding)
    rec = _adj.make_resolution(
        fid, verb="consumed",
        reason=f"regenerated fragment for section {sec!r} superseded its subject "
               f"(round {round}, packet {packet})",
        kind=finding.get("kind") or "", section=sec,
        actor=actor, round=int(round or 0), project=project)
    rec["consumed_by"] = {"round": int(round or 0), "packet": str(packet or ""),
                          "finding_kind": finding.get("kind") or "",
                          "finding_round": finding_round(finding)}
    path = ledger if ledger is not None else _feedback_path(repo, project)
    _append_jsonl(path, rec)
    return {"ok": True, "id": rec["id"], "supersedes": fid,
            "consumed_by": rec["consumed_by"]}
