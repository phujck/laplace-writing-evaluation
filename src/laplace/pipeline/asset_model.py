"""The asset model (P7) — every derivation and every figure an ADDRESSABLE OBJECT.

The author asked, repeatedly, for a surface where a derivation or a figure is an
object of work: fine-grained assessment (find against the *step* or the *panel*,
never only the whole asset) and banked edits (edit the source, bank with
provenance). It was designed 2026-07-14, the design was parked outside the repo,
and the piece was never built. This module is law 8 for that piece: **the store
the design doc renders from.** The doc (``DESIGN_2026-07-14_asset-work-suites-P7.md``)
describes; this enumerates the real objects off the real filesystem.

Two conventions map in WITHOUT moving a file (the ASSET ROOTS declaration below):

* the ``synthetics papers/`` convention — ``manuscript/figures/`` co-locates a
  ``.py`` generator + rendered ``.png``/``.pdf`` (producer ``py-script``); the
  derivation walks live as ``.tex`` files under
  ``manuscript/evolutions/*/derivation_walks/`` (producer ``tex-inline``);
* the ``eigenengine`` convention — ``figures/src/fig_*.tex`` hand-authored tikz
  (producer ``hand-tikz``), NO ``.py``, and NO derivation walks at all. Its
  ``derivations == []`` is DECLARED, not an error;
* the aspiration-first ISNAD convention (``derivation_organ``'s domain) —
  ``manuscript/aspiration/derivations/link-*.tex`` fragments, each joined to its
  ``chain.jsonl`` row (``attested``/``gap`` status, the claim, the ratified
  ``node_id``) via :func:`derivation_organ.read_chain`, never re-parsed here.
  Folded into EVERY registered project's roots generically (by directory
  identity — ``<manuscript>/aspiration/derivations`` — not a project name), so
  a project laid out this way is picked up without a new branch per project.

Design discipline:

* **filesystem-first + cheap.** ``enumerate_assets`` globs the figure dirs and
  the derivation-walk dirs, parses the ``\\begin{equation}...\\end{equation}``
  step structure of each walk, and — when a ``main.nodemap.json`` exists — wires
  the measured page landings in. Nothing here runs a compile or spends a token.
* **plain when unknown.** No nodemap → ``landings == []``. No generator →
  ``Producer(type="none", path=None)``. No data dependency → ``inputs == []``.
  A schematic figure and a data figure are distinguishable, not conflated.
* **ledger enrichment is optional.** The friction ledger's ``set-projection``
  provenance links a generator path to its ``fig:`` node (and thus its data
  inputs and the conceptric nodes it supports). When the ledger is present and
  parseable we enrich; when it is absent we still enumerate every figure off the
  disk. The producer path — the field the tests assert on — never depends on it.
* **pure at import.** No module-level filesystem or network work.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

log = logging.getLogger(__name__)


def _repo_root() -> Path:
    from laplace.pipeline import registry
    return registry._repo_root()


# --------------------------------------------------------------------------- #
# The schema — dataclasses the design doc renders from.
# --------------------------------------------------------------------------- #

#: producer kinds a figure/derivation may declare. ``none`` is HONEST — a figure
#: whose generator we cannot name is a real object with an unknown producer, not
#: an omitted one.
PRODUCER_TYPES = frozenset({"py-script", "hand-tikz", "tex-inline", "none"})

#: the only two asset kinds this model addresses.
ASSET_KINDS = frozenset({"figure", "derivation"})


@dataclass(frozen=True)
class Producer:
    """WHAT makes the asset. ``path`` is repo-relative; ``None`` iff type is ``none``."""

    type: str = "none"
    path: str | None = None

    def __post_init__(self) -> None:
        if self.type not in PRODUCER_TYPES:
            raise ValueError(
                f"Producer.type={self.type!r} not in {sorted(PRODUCER_TYPES)}"
            )

    @classmethod
    def from_dict(cls, d: dict) -> "Producer":
        return cls(type=d.get("type", "none"), path=d.get("path"))


@dataclass(frozen=True)
class Landing:
    """WHERE the asset lands in a rendered artefact — one measured page region.

    Mirrors a ``main.nodemap.json`` entry: ``kind`` (float/caption/equation/...),
    ``page`` (1-based), ``bbox`` ({x0,y0,x1,y1} in PDF points), plus the nodemap's
    measured-vs-inferred honesty carried through as ``measured`` (a real synctex
    box) vs inferred (float-marker + mirrored margin).
    """

    file: str                       # the artefact the region is measured in
    page: int | None = None
    bbox: dict | None = None        # {"x0","y0","x1","y1"}
    kind: str | None = None
    measured: bool | None = None    # True=synctex box, False=inferred width, None=unknown
    source: str = "nodemap"         # provenance of THIS landing record

    @classmethod
    def from_dict(cls, d: dict) -> "Landing":
        return cls(
            file=d.get("file", ""), page=d.get("page"), bbox=d.get("bbox"),
            kind=d.get("kind"), measured=d.get("measured"),
            source=d.get("source", "nodemap"),
        )


@dataclass(frozen=True)
class StepAnchor:
    """A fine-grained anchor INSIDE a derivation — one equation/align environment.

    ``id`` is the labelled equation (``eq:hl-sum``) when the walk labels it, else a
    stable synthetic (``WK-043#eq2``). This is the object a finding anchors to: a
    finding against a derivation names the STEP, never only the whole walk.
    """

    id: str
    kind: str = "equation"          # equation | align | gather | multline | ...
    label: str | None = None        # the \label{...} target, when present
    line_start: int | None = None   # 1-based line in the source
    line_end: int | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "StepAnchor":
        return cls(
            id=d["id"], kind=d.get("kind", "equation"), label=d.get("label"),
            line_start=d.get("line_start"), line_end=d.get("line_end"),
        )


@dataclass(frozen=True)
class PanelAnchor:
    """A fine-grained anchor INSIDE a figure — one subfigure/panel.

    ``id`` is a panel letter (``a``, ``b``, ``c`` ...). This is the object a
    finding anchors to: a finding against a figure names the PANEL, never only
    the whole figure. Best-effort off the producer source; empty when the figure
    is single-panel or the producer does not expose panels.
    """

    id: str
    label: str | None = None        # a nearby source label, when found
    var: str | None = None          # the producer variable (matplotlib axis), when known

    @classmethod
    def from_dict(cls, d: dict) -> "PanelAnchor":
        return cls(id=d["id"], label=d.get("label"), var=d.get("var"))


@dataclass
class AssetObject:
    """ONE addressable asset: a figure or a derivation, with its full provenance.

    The addressability contract (D1/F1): ``id``, ``kind``, ``project``,
    ``producer``, ``inputs``, ``nodes_supported``, ``landings``. The fine-grained
    contract (D2/F2): ``steps`` (derivations) and ``panels`` (figures). Every
    unknown is a declared empty, never a fabricated value.
    """

    id: str
    kind: str                       # figure | derivation
    project: str
    producer: Producer = field(default_factory=Producer)
    inputs: list[str] = field(default_factory=list)          # data/script deps
    nodes_supported: list[str] = field(default_factory=list)  # conceptric ids (all fig->node links)
    #: the TYPED demonstrates-axis subset: ``demonstrates::<result>`` tokens (minted
    #: through schema.token_for) for the results this figure DEMONSTRATES. A figure
    #: with a non-empty ``demonstrates`` is a demonstrating figure — distinguishable
    #: from one that merely decorates (nodes_supported present, demonstrates empty).
    demonstrates: list[str] = field(default_factory=list)
    landings: list[Landing] = field(default_factory=list)
    steps: list[StepAnchor] = field(default_factory=list)     # derivations only
    panels: list[PanelAnchor] = field(default_factory=list)   # figures only
    rendered: list[str] = field(default_factory=list)         # co-located png/pdf
    source_path: str | None = None  # the primary source file on disk (repo-relative)
    node_id: str | None = None      # linked conceptric node id, when known
    claim: str | None = None        # the isnad chain's target claim (aspiration links only)
    status: str | None = None       # attested | gap (aspiration isnad links only); else None
    #: The banked figure-manifest declaration, when one explicitly names this
    #: figure.  This is a join, not a second figure inventory: file discovery
    #: remains the authority for a render being present on disk.
    figure_identity: dict | None = None

    def __post_init__(self) -> None:
        if self.kind not in ASSET_KINDS:
            raise ValueError(f"AssetObject.kind={self.kind!r} not in {sorted(ASSET_KINDS)}")

    # -- JSON round-trip (the store the doc renders from must serialise cleanly) --
    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, d: dict) -> "AssetObject":
        return cls(
            id=d["id"], kind=d["kind"], project=d["project"],
            producer=Producer.from_dict(d.get("producer") or {}),
            inputs=list(d.get("inputs") or []),
            nodes_supported=list(d.get("nodes_supported") or []),
            demonstrates=list(d.get("demonstrates") or []),
            landings=[Landing.from_dict(x) for x in d.get("landings") or []],
            steps=[StepAnchor.from_dict(x) for x in d.get("steps") or []],
            panels=[PanelAnchor.from_dict(x) for x in d.get("panels") or []],
            rendered=list(d.get("rendered") or []),
            source_path=d.get("source_path"), node_id=d.get("node_id"),
            claim=d.get("claim"), status=d.get("status"),
            figure_identity=(dict(d["figure_identity"])
                             if isinstance(d.get("figure_identity"), dict) else None),
        )

    @classmethod
    def from_json(cls, s: str) -> "AssetObject":
        return cls.from_dict(json.loads(s))


# --------------------------------------------------------------------------- #
# THE ASSET ROOTS CONVENTION — the declaration this design defines.
#
# A project declares where its figure producers and its derivation walks live,
# and how its figures are produced. Both existing layouts map in with NO file
# moved. A project with no derivation walks declares ``derivations=[]`` — honest,
# first-class, not an error. Unknown projects fall back to the ``synthetics
# papers/`` convention derived from the registry Project record.
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class AssetRoots:
    """Where a project's assets live and how its figures are produced.

    ``figures`` / ``derivations`` are repo-relative dir globs. ``figure_producer``
    is ``auto`` (a ``.py`` generator is the producer, a rendered ``.png``/``.pdf``
    sibling is required — this rejects style helpers like ``figstyle.py``),
    ``hand-tikz`` (the ``.tex`` IS the producer, a rendered sibling is optional), or
    ``shared-script`` (rendered figures whose producer is one script declared on
    ``producer_script`` and living OUTSIDE the figures dir — the flagship layout where
    ``numerics/falqon_figures.py`` emits several ``.pdf`` renders into
    ``manuscript/figures``). ``nodemap`` is the ``main.nodemap.json`` path when present;
    ``producer_script`` is the repo-relative shared producer (``shared-script`` only).
    """

    figures: tuple[str, ...] = ()
    derivations: tuple[str, ...] = ()
    figure_producer: str = "auto"          # auto | hand-tikz | shared-script
    nodemap: str | None = None
    producer_script: str | None = None     # the one producer (shared-script layout only)


#: explicit declarations for the two layouts P7 must cover today. Everything else
#: is derived from the registry in :func:`asset_roots`.
ASSET_ROOTS: dict[str, AssetRoots] = {
    "subset-sum-itqde": AssetRoots(
        figures=("synthetics papers/subset-sum-itqde/manuscript/figures",),
        derivations=(
            "synthetics papers/subset-sum-itqde/manuscript/evolutions/*/derivation_walks",
        ),
        figure_producer="auto",
        # W-NODEMAPS (2026-07-22): the whitepaper now carries a built main.nodemap.json
        # (the compiled artefact lives under the plan target_dir …/whitepaper, where the
        # review surface reads it — NOT the bare manuscript dir). A figure asset whose
        # ledger node id matches a compiled \label lands off it; the rest read [] until
        # the asset ledger's fig ids are re-aligned to the whitepaper's \label ids (a
        # separate content seam — the ledger keeps fig:f1-staircase while the artefact
        # relabelled to fig:nf1). T1 (label) tier only: the paragraph tier's 154 markers
        # migrate floats in this two-column reprint layout and the drift gate refuses them.
        nodemap="synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.nodemap.json",
    ),
    "eigenengine": AssetRoots(
        figures=("eigenengine/figures/src",),
        derivations=(),  # declared: eigenengine has no derivation walks
        figure_producer="hand-tikz",
        nodemap="eigenengine/manuscript/main.nodemap.json",
    ),
    # paper_falqon (G2, 2026-07-22): the flagship layout the auto/hand-tikz conventions
    # miss — rendered .pdf figures land in manuscript/figures with NO co-located producer,
    # because one script (numerics/falqon_figures.py) emits BOTH fig_resources and
    # fig_witness from off-tree. Declared as shared-script so enumerate_assets stops
    # returning zero figures for the paper; each render's fig:<stem> resolves to the
    # nodemap landing (fig:resources p6, fig:witness p7). The derivation walks fold in
    # generically via the aspiration convention below.
    "paper_falqon": AssetRoots(
        figures=("paper_falqon/manuscript/figures",),
        derivations=(),
        figure_producer="shared-script",
        producer_script="paper_falqon/numerics/falqon_figures.py",
        nodemap="paper_falqon/manuscript/main.nodemap.json",
    ),
}


def asset_roots(project_name: str) -> AssetRoots | None:
    """Resolve a project's asset roots. Declared entries win; otherwise derive the
    ``synthetics papers/`` default from the registry (a conceptric project's
    figures live under ``manuscript/figures`` and its derivation walks under
    ``manuscript/evolutions/*/derivation_walks``). Unknown project → ``None``.

    Either way, ``<manuscript>/aspiration/derivations`` — the aspiration-first
    isnad convention's fragment store (``chain.jsonl`` + ``link-*.tex``,
    ``derivation_organ``'s domain) — is folded into ``derivations`` GENERICALLY,
    for every registered project that actually has one on disk (never a
    per-project hardcode: the check is ``is_dir()``, not a name match). A
    project with no aspiration store keeps exactly the roots it declared."""
    if project_name in ASSET_ROOTS:
        roots = ASSET_ROOTS[project_name]
        ms = None
        try:
            from laplace.pipeline import registry
            proj = registry.resolve(project_name)
            ms = proj.manuscript_dir if proj else None
        except Exception:  # registry read is best-effort; never hard-fail here
            ms = None
    else:
        try:
            from laplace.pipeline import registry
            proj = registry.resolve(project_name)
        except Exception:  # registry read is best-effort; never hard-fail here
            proj = None
        if proj is None or not proj.manuscript_dir:
            return None
        ms = proj.manuscript_dir
        nm = f"{ms}/main.nodemap.json"
        nm_ok = (_repo_root() / nm).is_file()
        roots = AssetRoots(
            figures=(f"{ms}/figures",),
            derivations=(f"{ms}/evolutions/*/derivation_walks",),
            figure_producer="auto",
            nodemap=nm if nm_ok else None,
        )
    if ms:
        asp = f"{ms}/aspiration/derivations"
        if asp not in roots.derivations and (_repo_root() / asp).is_dir():
            roots = replace(roots, derivations=roots.derivations + (asp,))
    return roots


# --------------------------------------------------------------------------- #
# Producer/source parsing helpers (pure text; no compile, no import of sources).
# --------------------------------------------------------------------------- #

_FIG_RENDER_EXTS = (".png", ".pdf", ".svg", ".jpg", ".jpeg", ".webp")
#: matplotlib-style helpers that are NOT figures even though they are .py in a
#: figures dir (they render nothing themselves). The rendered-sibling rule already
#: rejects these; the set is a belt-and-braces guard for style/util modules.
_STYLE_HELPERS = frozenset({"figstyle", "conftest", "__init__", "setup", "_util", "common"})

# equation-family environments that constitute a derivation STEP
_EQ_ENVS = ("equation", "align", "gather", "multline", "eqnarray", "flalign", "dmath")
_BEGIN_RX = re.compile(r"\\begin\{(" + "|".join(_EQ_ENVS) + r")\*?\}")
_END_RX = re.compile(r"\\end\{(" + "|".join(_EQ_ENVS) + r")\*?\}")
_LABEL_RX = re.compile(r"\\label\{([^}]+)\}")
#: the WK-walk lead comment: ``% WK-043-derive -> thm:hardy-littlewood-collapse``
_WK_SUPPORTS_RX = re.compile(r"->\s*([a-z][\w-]*:[\w:-]+)")
_WK_NUM_RX = re.compile(r"(WK-\d+)")
#: matplotlib panel creation, for the best-effort panel extractor
_SUBPLOT_RX = re.compile(r"(\w+)\s*=\s*\w+\.add_subplot\(")
_SUBPLOTS_RX = re.compile(r"\.subplots\(\s*(\d+)\s*,\s*(\d+)")


def _rel(p: Path) -> str:
    """repo-relative POSIX string, falling back to the absolute path off-tree."""
    root = _repo_root()
    try:
        return p.resolve().relative_to(root).as_posix()
    except ValueError:
        return p.as_posix()


def _parse_steps(tex_path: Path) -> tuple[list[StepAnchor], list[str]]:
    """Parse a derivation walk into step anchors + the nodes it supports.

    Steps: one anchor per equation-family environment; id = its ``\\label`` when
    present, else a synthetic ``WK-NNN#eqK``. Supported nodes: the ``-> node:id``
    targets in the lead comment.
    """
    try:
        text = tex_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], []
    lines = text.splitlines()
    wk = _WK_NUM_RX.search(tex_path.stem)
    wk_id = wk.group(1) if wk else tex_path.stem

    # supported nodes from the lead comment(s) (first non-empty comment lines)
    supports: list[str] = []
    for ln in lines[:5]:
        if ln.lstrip().startswith("%"):
            for m in _WK_SUPPORTS_RX.finditer(ln):
                if m.group(1) not in supports:
                    supports.append(m.group(1))

    steps: list[StepAnchor] = []
    i, n, eq_ct = 0, len(lines), 0
    while i < n:
        mb = _BEGIN_RX.search(lines[i])
        if not mb:
            i += 1
            continue
        env = mb.group(1)
        start = i
        label = None
        j = i
        while j < n:
            ml = _LABEL_RX.search(lines[j])
            if ml and label is None:
                label = ml.group(1)
            if _END_RX.search(lines[j]):
                break
            j += 1
        eq_ct += 1
        steps.append(StepAnchor(
            id=label or f"{wk_id}#eq{eq_ct}",
            kind=env, label=label,
            line_start=start + 1, line_end=j + 1,
        ))
        i = j + 1
    return steps, supports


def _parse_panels(producer: Path) -> list[PanelAnchor]:
    """Best-effort panel extraction off a figure producer source.

    matplotlib producers: one panel per ``ax = fig.add_subplot(...)`` (named), or
    the grid implied by ``.subplots(r, c)``. hand-tikz/other: no reliable panel
    signal → ``[]`` (single-panel or unknown, plain)."""
    try:
        text = producer.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    letters = "abcdefghijklmnop"
    vars_ = _SUBPLOT_RX.findall(text)
    if vars_:
        # de-dup preserving order (a var may be reassigned across the script)
        seen: list[str] = []
        for v in vars_:
            if v not in seen:
                seen.append(v)
        return [PanelAnchor(id=letters[k], var=v) for k, v in enumerate(seen)
                if k < len(letters)]
    ms = _SUBPLOTS_RX.search(text)
    if ms:
        count = int(ms.group(1)) * int(ms.group(2))
        if count > 1:
            return [PanelAnchor(id=letters[k]) for k in range(min(count, len(letters)))]
    return []


# --------------------------------------------------------------------------- #
# Ledger enrichment (optional, guarded) — link a figure file to its conceptric
# node via the set-projection provenance, then read its data inputs and the nodes
# it supports off the same ledger. Absent/unparseable ledger → no enrichment, and
# every figure still enumerates off the disk.
# --------------------------------------------------------------------------- #

def _ledger_path(project_name: str) -> Path | None:
    try:
        from laplace.pipeline import registry
        proj = registry.resolve(project_name)
    except Exception:
        proj = None
    if proj and proj.ledger:
        p = _repo_root() / proj.ledger
        return p if p.is_file() else None
    # fall back to the conventional location
    p = _repo_root() / "corpus_friction" / f"{project_name}.jsonl"
    return p if p.is_file() else None


def _load_ledger_enrichment(project_name: str) -> dict:
    """Build ``{by_generator_basename, supported_by_node}`` off the friction ledger.

    * ``by_generator_basename[<file.py>] = {node, inputs, kind}`` — from
      ``set-projection`` provenance (``generator`` → its ``fig:`` node, data files,
      schematic-vs-data).
    * ``supported_by_node[<fig:id>] = [target, ...]`` — from ``add-edge`` ops
      whose ``node`` is the figure (the concepts the figure illustrates).
    * ``demonstrated_by_node[<node>] = [demonstrates::target, ...]`` — the TYPED
      demonstrates-axis tokens (minted through :func:`schema.token_for`) for the
      results a figure DEMONSTRATES (an ``add-edge`` carrying ``axis="demonstrates"``).
    """
    from laplace.pipeline.schema import token_for
    out = {"by_generator_basename": {}, "supported_by_node": {},
           "demonstrated_by_node": {}}
    path = _ledger_path(project_name)
    if path is None:
        return out
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    by_gen = out["by_generator_basename"]
    supp = out["supported_by_node"]
    dem = out["demonstrated_by_node"]
    for line in raw:
        line = line.strip()
        if not line:
            continue
        try:
            op = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = op.get("kind")
        if kind == "add-edge":
            node = op.get("node", "")
            tgt = op.get("target")
            axis = (op.get("axis") or "").strip()
            # nodes_supported collects every fig:->target link (the concepts the
            # figure relates to). The gate WIDENS past the hard fig: prefix WHERE
            # SAFE: an edge explicitly typed axis="demonstrates" names a figure by
            # the axis registry ("a figure bears a result") whatever its id prefix,
            # so a figure whose node id is not fig:-prefixed still registers.
            typed_dem = axis == "demonstrates"
            if tgt and (node.startswith("fig:") or typed_dem):
                supp.setdefault(node, [])
                if tgt not in supp[node]:
                    supp[node].append(tgt)
                # the TYPED demonstrates subset — an explicit demonstrates-axis edge
                # marks a figure that DEMONSTRATES its result (vs one that decorates).
                # The token is minted through the ONE HOME, never a hand-written prefix.
                if typed_dem:
                    tok = token_for("demonstrates", tgt)
                    dem.setdefault(node, [])
                    if tok not in dem[node]:
                        dem[node].append(tok)
        elif kind == "set-projection":
            val = op.get("value") or {}
            prov = val.get("provenance") if isinstance(val, dict) else None
            if not isinstance(prov, dict):
                continue
            gen = prov.get("generator")
            if not gen:
                continue
            base = Path(gen).name
            inputs: list[str] = list(prov.get("data_files") or [])
            for extra_key in ("engine", "config"):
                v = prov.get(extra_key)
                if v and v not in inputs:
                    inputs.append(v)
            by_gen[base] = {
                "node": op.get("node"),
                "inputs": inputs,
                "prov_kind": prov.get("kind"),   # schematic | data
            }
    return out


# --------------------------------------------------------------------------- #
# Nodemap landings.
# --------------------------------------------------------------------------- #

def _load_nodemap(rel: str | None) -> tuple[dict, str]:
    """Load a ``main.nodemap.json``. Returns ``(entries, artefact)`` where
    ``entries`` is node_id → [region...] and ``artefact`` is the manuscript file
    the regions are measured in (the map's ``main_tex``, resolved repo-relative to
    the map's own dir). Missing/unparseable → ``({}, "")``."""
    if not rel:
        return {}, ""
    p = _repo_root() / rel
    if not p.is_file():
        return {}, ""
    try:
        doc = json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return {}, ""
    entries = doc.get("entries", {}) or {}
    main_tex = doc.get("main_tex") or ""
    # the artefact lives alongside the map (…/manuscript/main.tex)
    artefact = _rel((p.parent / main_tex)) if main_tex else _rel(p)
    return entries, artefact


def _landings_for(node_id: str | None, entries: dict, artefact: str) -> list[Landing]:
    if not node_id or node_id not in entries or not artefact:
        return []
    out: list[Landing] = []
    for r in entries[node_id]:
        bbox = None
        if all(k in r for k in ("x0", "y0", "x1", "y1")):
            bbox = {"x0": r["x0"], "y0": r["y0"], "x1": r["x1"], "y1": r["y1"]}
        width = r.get("width")
        measured = (width == "measured") if width in ("measured", "inferred") else None
        out.append(Landing(
            file=artefact, page=r.get("page"), bbox=bbox,
            kind=r.get("kind"), measured=measured, source="nodemap",
        ))
    return out


# --------------------------------------------------------------------------- #
# Discovery.
# --------------------------------------------------------------------------- #

def _iter_dirs(globs: tuple[str, ...]) -> list[Path]:
    root = _repo_root()
    dirs: list[Path] = []
    for g in globs:
        # a glob with a wildcard is resolved against the repo root; a plain path
        # is taken as-is.
        if any(ch in g for ch in "*?["):
            dirs.extend(sorted(p for p in root.glob(g) if p.is_dir()))
        else:
            p = root / g
            if p.is_dir():
                dirs.append(p)
    return dirs


def _figure_manifest_identities(roots: AssetRoots) -> dict[str, dict]:
    """Map a rendered basename to its *declared* figure-manifest identity.

    ``figure_manifest.json`` is already the figures organ's banked truth.  The
    asset view used to discover the same render independently and therefore
    discarded its promise/generator/label identity.  This narrow join makes the
    declaration visible without guessing from names or making a GET run figures.
    A future manifest may supply ``asset_id``; historical manifests are joined
    through their explicit ``artefact`` field.
    """
    if not roots.figures:
        return {}
    # Figure roots and manuscript root are conventionally siblings.  Registry
    # supplied roots may be nested, so walk upward only until a manifest is
    # found; this is bounded by the declared path, never a repository scan.
    root = _repo_root()
    manifests: list[Path] = []
    for rel in roots.figures:
        p = root / rel
        for candidate in (p.parent / "figure_manifest.json", p.parent.parent / "figure_manifest.json"):
            if candidate.is_file() and candidate not in manifests:
                manifests.append(candidate)
    identities: dict[str, dict] = {}
    for manifest in manifests:
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        for row in raw.get("placed") or []:
            if not isinstance(row, dict) or not isinstance(row.get("artefact"), str):
                continue
            name = Path(row["artefact"]).name
            if not name:
                continue
            identities[name] = {
                "asset_id": row.get("asset_id"), "label": row.get("label"),
                "promise": row.get("promise"), "generator": row.get("generator"),
                "matched": row.get("matched"), "manifest": _rel(manifest),
            }
    return identities


def _discover_figures(project_name: str, roots: AssetRoots,
                      entries: dict, artefact: str, ledger: dict) -> list[AssetObject]:
    assets: list[AssetObject] = []
    seen_stems: set[tuple[str, str]] = set()  # (dir, stem)
    by_gen = ledger.get("by_generator_basename", {})
    supp = ledger.get("supported_by_node", {})
    dem = ledger.get("demonstrated_by_node", {})
    manifest_identities = _figure_manifest_identities(roots)

    for d in _iter_dirs(roots.figures):
        files = sorted(d.iterdir())
        generated = d / "generated"
        if generated.is_dir():
            files += sorted(generated.iterdir())
        stems: dict[str, dict] = {}   # stem -> {py, tex, renders[]}
        for f in files:
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            stem = f.stem
            slot = stems.setdefault(stem, {"py": None, "tex": None, "renders": []})
            if ext == ".py":
                slot["py"] = f
            elif ext == ".tex":
                slot["tex"] = f
            elif ext in _FIG_RENDER_EXTS:
                slot["renders"].append(f)

        for stem, slot in sorted(stems.items()):
            key = (d.name, stem)
            if key in seen_stems:
                continue
            if stem.lower() in _STYLE_HELPERS:
                continue
            py, tex, renders = slot["py"], slot["tex"], slot["renders"]

            # choose producer + apply the include rule per figure_producer discipline
            if roots.figure_producer == "shared-script":
                # a rendered figure whose producer is ONE declared script off-tree; the
                # render itself is the addressable object (no .py/.tex sibling needed).
                if not renders:
                    continue  # nothing rendered here is not an addressable figure
                producer = Producer("py-script", roots.producer_script)
                source = None  # the shared script produces several figures; no per-figure panels
                base_stem = stem[4:] if stem.startswith("fig_") else stem
                node_id = f"fig:{base_stem}"
            elif roots.figure_producer == "hand-tikz":
                if tex is None:
                    continue  # a hand-tikz root asset must have its .tex
                producer = Producer("hand-tikz", _rel(tex))
                source = tex
                # node id: fig_<stem>.tex -> fig:<stem>
                base_stem = stem[4:] if stem.startswith("fig_") else stem
                node_id = f"fig:{base_stem}"
            else:  # "auto": py generator is the producer, render sibling required
                if py is not None:
                    if not renders:
                        continue  # a .py with no rendered output is a helper, not a figure
                    producer = Producer("py-script", _rel(py))
                    source = py
                    node_id = None  # resolved from the ledger below
                elif tex is not None and renders:
                    producer = Producer("hand-tikz", _rel(tex))
                    source = tex
                    node_id = None
                elif renders and any(Path(r).name in manifest_identities for r in renders):
                    # Explicit visual-spec/manifest declarations are legitimate
                    # producers even though they intentionally have no sibling script.
                    identity = next(manifest_identities[Path(r).name] for r in renders if Path(r).name in manifest_identities)
                    producer = Producer("py-script", identity.get("manifest"))
                    source = None; node_id = None
                else:
                    continue  # no producer + no render → not an addressable figure

            seen_stems.add(key)

            # ledger link (auto figures): generator basename -> fig node + inputs
            inputs: list[str] = []
            nodes_supported: list[str] = []
            demonstrates: list[str] = []
            if producer.path is not None:
                base = Path(producer.path).name
                link = by_gen.get(base)
                if link:
                    node_id = link.get("node") or node_id
                    inputs = list(link.get("inputs") or [])
            if node_id and node_id in supp:
                nodes_supported = list(supp[node_id])
            if node_id and node_id in dem:
                demonstrates = list(dem[node_id])       # the typed demonstrates tokens

            landings = _landings_for(node_id, entries, artefact)
            # a shared-script figure has no per-figure source (one script, many figures) →
            # no panel signal and the producer path stands as the source.
            panels = _parse_panels(source) if source is not None else []
            rendered = [_rel(r) for r in sorted(renders)]
            source_path = _rel(source) if source is not None else producer.path
            figure_identity = next((manifest_identities.get(Path(r).name)
                                    for r in rendered if Path(r).name in manifest_identities), None)
            # A manifest may explicitly assign a public asset id.  It wins over
            # the historical file-stem convention, but an invalid/non-string id
            # is ignored instead of inventing a replacement.
            asset_id = (figure_identity or {}).get("asset_id")
            if not isinstance(asset_id, str) or not asset_id.strip():
                asset_id = f"figure:{stem}"

            assets.append(AssetObject(
                id=asset_id, kind="figure", project=project_name,
                producer=producer, inputs=inputs, nodes_supported=nodes_supported,
                demonstrates=demonstrates,
                landings=landings, panels=panels, rendered=rendered,
                source_path=source_path, node_id=node_id,
                figure_identity=figure_identity,
            ))
    return assets


def _is_aspiration_dir(d: Path) -> bool:
    """``True`` for ``<manuscript>/aspiration/derivations`` — the isnad-fragment
    convention, identified by DIRECTORY IDENTITY (never a project name), so any
    project laid out this way is picked up without a new branch per project."""
    return d.name == "derivations" and d.parent.name == "aspiration"


def _discover_walk_derivations(project_name: str, d: Path) -> list[AssetObject]:
    """The ``synthetics papers/`` WK-NNN convention: one asset per walk file, its
    steps parsed off the ``\\begin{equation}...\\end{equation}`` structure."""
    assets: list[AssetObject] = []
    for f in sorted(d.glob("*.tex")):
        if not f.is_file():
            continue
        steps, supports = _parse_steps(f)
        wk = _WK_NUM_RX.search(f.stem)
        aid = wk.group(1) if wk else f.stem
        assets.append(AssetObject(
            id=f"derivation:{aid}", kind="derivation", project=project_name,
            producer=Producer("tex-inline", _rel(f)),
            inputs=[], nodes_supported=supports, landings=[],
            steps=steps, source_path=_rel(f), node_id=None,
        ))
    return assets


def _discover_isnad_derivations(project_name: str, d: Path) -> list[AssetObject]:
    """The aspiration-first isnad convention: ``link-*.tex`` fragments under
    ``<manuscript>/aspiration/derivations``, each joined to its ``chain.jsonl``
    row via :func:`derivation_organ.read_chain` — the one reader, never
    re-parsed here. A fragment with no chain row (banked ahead of its isnad
    entry) still enumerates, plainly ``status=None``. ``computed/<link>.*``
    siblings (a forged computation's output) ride ``rendered`` when present."""
    from laplace.pipeline import derivation_organ

    ms = d.parent.parent  # <manuscript>/aspiration/derivations -> <manuscript>
    try:
        chain_by_id = {l["id"]: l for l in derivation_organ.read_chain(ms) if l.get("id")}
    except Exception:  # a malformed chain never blocks the fragments off disk
        chain_by_id = {}
    computed_dir = d.parent / "computed"

    assets: list[AssetObject] = []
    for f in sorted(d.glob("*.tex")):
        if not f.is_file():
            continue
        steps, _ = _parse_steps(f)
        link_id = f.stem
        link = chain_by_id.get(link_id, {})
        rendered: list[str] = []
        if computed_dir.is_dir():
            rendered = sorted(_rel(p) for p in computed_dir.glob(f"{link_id}.out.*")
                              if p.is_file())
        assets.append(AssetObject(
            id=f"derivation:{link_id}", kind="derivation", project=project_name,
            producer=Producer("tex-inline", _rel(f)),
            inputs=[], nodes_supported=[], landings=[],
            steps=steps, rendered=rendered, source_path=_rel(f),
            node_id=link.get("node_id"),
            claim=link.get("to") or None, status=link.get("status"),
        ))
    return assets


def _discover_derivations(project_name: str, roots: AssetRoots) -> list[AssetObject]:
    assets: list[AssetObject] = []
    for d in _iter_dirs(roots.derivations):
        if _is_aspiration_dir(d):
            assets.extend(_discover_isnad_derivations(project_name, d))
        else:
            assets.extend(_discover_walk_derivations(project_name, d))
    return assets


def enumerate_assets(project_name: str) -> list[AssetObject]:
    """Every figure and derivation of ``project_name`` as an addressable object.

    Filesystem-first and cheap: globs the declared figure/derivation roots, parses
    each derivation walk's step structure, wires nodemap landings when a
    ``main.nodemap.json`` exists, and enriches figures with ledger provenance when
    the friction ledger is present. Declared empties throughout when a fact is not
    on disk. Returns ``[]`` for an unknown project or absent roots — never raises
    for a missing directory.
    """
    roots = asset_roots(project_name)
    if roots is None:
        return []
    entries, artefact = _load_nodemap(roots.nodemap)
    ledger = _load_ledger_enrichment(project_name)
    figs = _discover_figures(project_name, roots, entries, artefact, ledger)
    ders = _discover_derivations(project_name, roots)
    out = figs + ders
    out.sort(key=lambda a: (a.kind, a.id))
    return out
