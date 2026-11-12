"""The project registry — every path the pipeline touches, resolved through ONE door.

Before this module the registry was 70% convention: a hardcoded corpus→tex-root
dict in ``corpus_ingest`` named the tex roots, ``shared_ui.plan_path_for``
derived the plan path from a layout convention, and every script hardcoded its
own subset-sum defaults (the calcification class the 2026-07-08 mandate names).
This formalises the convention as a :class:`Project` record with per-project
overrides, so a project whose layout differs (``paper_eigen``'s markdown loop,
``eigenengine``'s bare tex) registers instead of growing a parallel bespoke path.

That dict is GONE (2026-08-04): its six surviving keys are ordinary
:data:`DATA_PROJECTS_FILE` rows, so the corpus→tex-root map is DATA and a
project is registered the same way whether it was born in 2026 or this morning.
Corpus names are unchanged (the viewer's ``?corpus=`` param and the
friction-ledger filenames key off them). Unknown names resolve to ``None`` — a
traversal-shaped name never reaches the filesystem (the same fence
``plan_path_for`` kept).
"""

from __future__ import annotations
from laplace.core.checkout import repo_root as serving_checkout

import json
import logging
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def _repo_root() -> Path:
    return serving_checkout()


#: the layout families a Project may declare (frictions RW-...-400014): derived
#: from the kinds actually assigned in _projects() below, not aspirational -
#: adding a new layout means adding a member here in the same change.
KINDS = frozenset({"conceptric", "loop", "tex", "site", "project"})


@dataclass(frozen=True)
class Project:
    """One registered project: every repo-relative path the pipeline needs.

    ``kind`` names the layout family:
      ``conceptric`` — full pipeline: L1 friction ledger + plan + storyboard +
                       whitepaper (the ``synthetics papers/`` convention)
      ``project``    — source-optional workspace, with an optional manuscript capability
      ``loop``       — markdown bundle loop (paper_eigen: ``_loop/`` + gates)
      ``tex``        — bare tex manuscript, no conceptric substrate (ssg-disclosure)
      ``site``       — a website project in a SIBLING repo (the author's site):
                       its substrate is his public identity, not a conceptric;
                       ``external_root`` points at the sibling clone and every
                       path accessor resolves under it (F6, ruled 2026-07-11)

    ``manifest`` is the row's LAYOUT MANIFEST (the marriage law, 2026-07-28) — where this
    project keeps its ledger, projection and run-state, and its maps keyed by axis. See
    :data:`MANIFEST_KEYS` and :func:`married`.
    """

    name: str
    kind: str = "conceptric"
    external_root: str = ""               # kind="site": sibling-repo root, rel to OUR repo root
    project_dir: str = ""
    tex_root: str = ""                    # the corpus tex root (the atomiser input)
    ledger: str = ""                      # L1: corpus_friction/<name>.jsonl
    manuscript_dir: str = ""
    plan_path: str = ""                   # L2 reduced plan (committed)
    target_dir: str = ""                  # where compiled sections live
    briefs_dir: str = ""
    glossary: str = ""
    bib: str = "corpus/corpus.bib"        # the GLOBAL literature store
    feedback_ledger: str = ""             # declared pipeline feedback, not selected-source intake
    versions_dir: str = ""
    evolutions_dir: str = ""
    loop_dir: str = ""                    # kind="loop" only
    evidence_store: str = ""              # the numerics/readings dir a validates edge
                                          # dereferences into (falqon's numerics/);
                                          # additive — a coverage gauge's registry door
    gates_profile: dict = field(default_factory=dict)
    manifest: dict = field(default_factory=dict)   # the layout manifest (see MANIFEST_KEYS)

    def __post_init__(self) -> None:
        # RW-...-400014: kind was free text, validated nowhere, so a typo'd
        # kind (e.g. "slides") routed silently to no backend and failed late
        # at the driver instead of here at resolve(). A frozen dataclass can
        # still validate in __post_init__ as long as it only raises (no
        # object.__setattr__ needed).
        if self.kind not in KINDS:
            raise ValueError(
                f"Project(name={self.name!r}).kind={self.kind!r} is not a "
                f"known layout family; valid kinds are {sorted(KINDS)}"
            )

    # -- absolute-path accessors (the only place repo_root is applied) --------

    #: rels under these prefixes are the ENGINE's shared stores and never move to
    #: a sibling repo, even for kind="site": the friction ledger and the global
    #: literature store live where the drain and the pipeline live. Everything
    #: else on an external-rooted project is site content and rides external_root.
    _ENGINE_SIDE = ("corpus_friction/", "corpus/")

    def path(self, rel: str, repo_root: Path | None = None) -> Path | None:
        if not rel:
            return None
        root = repo_root or _repo_root()
        if rel.startswith("../"):
            # RW-...-553836: a rel naming a SIBLING repo (kind="site"'s
            # external_root, or any caller passing a raw sibling-relative rel)
            # cannot resolve under root — it lives beside it. The constraint:
            # a remote session's root holds the repo with sibling clones
            # checked out ALONGSIDE it, so the session root is root.parent,
            # not root itself. Guarded: never hand back a path that doesn't
            # exist on disk — a typo'd sibling name must raise loud here, not
            # route silently to a phantom location the caller trusts.
            sibling = (root / rel).resolve()
            if not sibling.exists():
                raise FileNotFoundError(
                    f"sibling path {rel!r} does not resolve under "
                    f"{root.parent} (tried {sibling}); the sibling clone "
                    f"must exist beside the repo root for cross-repo kinds"
                )
            return sibling
        if self.external_root and not rel.startswith(self._ENGINE_SIDE):
            return root / self.external_root / rel
        return root / rel

    def plan(self, repo_root: Path | None = None) -> Path | None:
        return self.path(self.plan_path, repo_root)

    def read_plan(self, repo_root: Path | None = None) -> dict | None:
        p = self.plan(repo_root)
        if p is None or not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            # exists-but-unparseable is a corruption to SURFACE (a truncated write, a
            # merge marker); an absent plan is silent above. Both return None, but only
            # the corrupt one warns - a silent None on corruption reads as "no plan".
            logging.warning("registry: plan %s exists but is unparseable: %s", p, e)
            return None

    def resolved_target_dir(self, repo_root: Path | None = None) -> Path | None:
        """The compiled-sections dir: ``plan.meta.target_dir`` when the plan
        declares it (the authored truth), else the registered convention."""
        plan = self.read_plan(repo_root)
        rel = ((plan or {}).get("meta") or {}).get("target_dir") or self.target_dir
        return self.path(rel, repo_root)

    def stage_path(self, key: str, repo_root: Path | None = None) -> Path | None:
        """A staged-pipeline artifact path (``schema.STAGE_ARTIFACTS``) under the
        manuscript dir — the 2026-07-09 rebuild's artifact convention."""
        from laplace.pipeline import schema
        rel = schema.STAGE_ARTIFACTS.get(key)
        if not rel or not self.manuscript_dir:
            return None
        return self.path(f"{self.manuscript_dir}/{rel}", repo_root)

    def content_homes(self, repo_root: Path | None = None) -> tuple[Path, ...]:
        """The resolved directories this project's content occupies (its project and manuscript homes).

        Resolution goes through :meth:`path`, so an ``external_root`` project (kind ``site``) owns homes under
        its sibling clone, never the engine checkout that its ``"."`` rel would name if it were joined to the
        repo root directly. A sibling rel that does not exist contributes no home (``path`` refuses it).
        """
        root = Path(repo_root) if repo_root is not None else _repo_root()
        homes: list[Path] = []
        for rel in (self.project_dir, self.manuscript_dir):
            if not rel:
                continue
            try:
                home = self.path(rel, root)
            except FileNotFoundError:
                continue
            if home is not None:
                homes.append(home.resolve())
        return tuple(dict.fromkeys(homes))


#: Local project declarations, including projects with no manuscript yet. Legacy
#: specialized layouts are compatibility fallbacks only where their content home
#: exists; an explicit data row always wins a same-name collision. An absent or
#: malformed file contributes no declarations and does not import phantom projects.
DATA_PROJECTS_FILE = "registry_projects.json"


def _data_projects(repo_root: Path) -> list[dict]:
    """The ``registry_projects.json`` rows, or ``[]`` (absent / unparseable / wrong shape —
    a data-source hiccup never crashes the registry; only present compatibility homes remain)."""
    p = repo_root / DATA_PROJECTS_FILE
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logging.warning("registry: %s exists but is unparseable: %s", DATA_PROJECTS_FILE, e)
        return []
    rows = data.get("projects") if isinstance(data, dict) else data
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _conceptric(name: str, tex_root: str, manifest: dict | None = None,
                project_dir: str | None = None, evidence_store: str | None = None) -> Project:
    """The ``synthetics papers/`` convention, stated once. A data row may override
    ``project_dir`` when its real home is elsewhere (design-interface lives under
    ``design_conceptric/``, not ``synthetics papers/`` — the deposit leg was checking
    a directory the project never occupied); the manuscript home then follows the
    row's own tex_root instead of the convention's derived path."""
    pd = (project_dir.strip("/") if isinstance(project_dir, str) and project_dir.strip()
          else f"synthetics papers/{name}")
    ms = tex_root if project_dir else f"{pd}/manuscript"
    return Project(
        name=name, kind="conceptric", project_dir=pd, tex_root=tex_root,
        manifest=manifest if isinstance(manifest, dict) else {},
        ledger=f"corpus_friction/{name}.jsonl",
        manuscript_dir=ms,
        plan_path=f"{ms}/projection_plan.json",
        target_dir=f"{ms}/whitepaper",
        briefs_dir=f"{ms}/briefs",
        glossary=f"{pd}/GLOSSARY.md",
        evidence_store=evidence_store if isinstance(evidence_store, str) else "",
        feedback_ledger=f"{ms}/whitepaper/feedback/feedback.jsonl",
        versions_dir=f"{ms}/versions",
        evolutions_dir=f"{ms}/evolutions",
    )


PLANNING_FIELDS = frozenset({"owner", "plan_path", "declared", "selection_identity", "by", "publication", "journal_offset",
                             "journal_anchor"})
# The declaration's bounded file-and-cut identity of contract/talk.jsonl (writing.project_lifecycle._cut_anchor):
# the file's device:inode ("" when no journal existed) and the sha256 of at most this many bytes before the cut.
PLANNING_ANCHOR_BYTES = 64 << 10
PLANNING_ANCHOR_FIELDS = frozenset({"file", "cut_sha256", "cut_bytes"})


def planning_declaration_problem(planning: object, manuscript_dir: str) -> str | None:
    """None when ``planning`` is exactly the reader-plan declaration writing.project_lifecycle makes for a
    project whose manuscript home is ``manuscript_dir``; otherwise what is wrong. One validator for the registry
    and the lifecycle owner: an unknown owner, another path, a missing declaration identity or attribution, or any
    extra field is never honoured and never silently reused or overwritten."""
    import re
    if not isinstance(planning, dict):
        return "the planning declaration is not an object"
    if set(planning) != PLANNING_FIELDS:
        return "the planning declaration fields are not exactly " + ",".join(sorted(PLANNING_FIELDS))
    # total over any decoded JSON: every type is checked before a comparison, pattern or membership test
    wrong = sorted(key for key in PLANNING_FIELDS - {"journal_offset", "journal_anchor"} if not isinstance(planning[key], str))
    if wrong:
        return "the planning declaration fields " + ",".join(wrong) + " are not text"
    offset = planning["journal_offset"]
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        return "the planning declaration has no valid journal offset (a non-negative integer)"
    anchor = planning["journal_anchor"]
    if not isinstance(anchor, dict) or set(anchor) != PLANNING_ANCHOR_FIELDS:
        return "the planning declaration has no valid journal anchor (fields " + ",".join(sorted(PLANNING_ANCHOR_FIELDS)) + ")"
    cut = anchor["cut_bytes"]
    if (not isinstance(anchor["file"], str) or not re.fullmatch(r"(?:[0-9]+:[0-9]+)?", anchor["file"])
            or not isinstance(anchor["cut_sha256"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", anchor["cut_sha256"])
            or not isinstance(cut, int) or isinstance(cut, bool) or cut != min(offset, PLANNING_ANCHOR_BYTES)
            or (anchor["file"] == "" and offset != 0)):
        return "the planning declaration's journal anchor does not describe its own cut"
    if planning["owner"] != "project_structure":
        return "the planning declaration names another owner"
    if planning["plan_path"] != f"{manuscript_dir}/projection_plan.json":
        return "the planning declaration names another plan path"
    if not re.fullmatch(r"PLAN-OWN-[0-9a-f]{32}", planning["declared"]):
        return "the planning declaration has no valid declaration identity"
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", planning["selection_identity"]):
        return "the planning declaration has no valid selection attribution"
    if planning["by"] not in ("author", "agent"):
        return "the planning declaration has no valid actor attribution"
    if planning["publication"] not in ("PENDING", "PUBLISHED"):
        return "the planning declaration has an unknown publication state"
    return None


def _build_registry(root: Path) -> tuple[dict[str, Project], dict[str, str]]:
    """The one registry merge, WITH provenance. Returns ``(registry, provenance)``
    where ``provenance[name]`` names the winning record. Explicit ``registry-row``
    declarations take precedence. A legacy ``hardcoded-block`` is a compatibility
    fallback only when its own content directory exists under the supplied root
    (or its explicitly configured external root).

    There were three layers until 2026-08-04: a ``corpora-legacy`` middle layer read
    the hardcoded ``corpus_ingest`` corpus→tex-root dict. That dict is deleted and its
    six surviving keys are data rows, so a finished paper and a project born through
    the dashboard door this morning now enter the registry by exactly one route."""
    reg: dict[str, Project] = {}
    prov: dict[str, str] = {}
    # Explicit declarations remain visible even before a manuscript is created.
    # Compatibility layouts below cannot override these local rows.
    for row in _data_projects(root):
        name = row.get("name")
        if not name or "/" in name or "\\" in name or ".." in name:
            continue    # a path-shaped data name never reaches the registry (the resolve fence)
        tex_root = row.get("tex_root") or f"synthetics papers/{name}/manuscript"
        if Path(tex_root).is_absolute() or ".." in Path(tex_root).parts:
            continue    # a path-shaped tex_root never reaches the registry either (the
            # G0 judge's catch: the name fence alone left a data-row tex_root free to
            # escape the repo root through resolve_corpus and its callers)
        pd_override = row.get("project_dir")
        if isinstance(pd_override, str) and pd_override.strip():
            if Path(pd_override).is_absolute() or ".." in Path(pd_override).parts:
                continue    # the same escape fence as tex_root: an absolute or
                # parent-walking project_dir never reaches the registry
        else:
            pd_override = None
        try:
            evidence_store = row.get("evidence_store")
            if isinstance(evidence_store, str) and evidence_store.strip():
                if Path(evidence_store).is_absolute() or ".." in Path(evidence_store).parts:
                    continue
            if row.get("kind") == "project":
                if not pd_override:
                    continue
                ms = f"{pd_override}/manuscript"
                manifest = row.get("manifest") if isinstance(row.get("manifest"), dict) else {}
                # PLAN OWNERSHIP (writing.project_lifecycle): a source-optional project that started authoring
                # declares its one plan at its own manuscript home. Only an exact, published declaration is
                # honoured (planning_declaration_problem); the layout, state home and every other path of the
                # record stay those of kind "project".
                planning = manifest.get("planning")
                plan_path = (f"{ms}/projection_plan.json" if planning is not None
                             and planning_declaration_problem(planning, ms) is None
                             and planning["publication"] == "PUBLISHED" else "")
                reg[name] = Project(name=name, kind="project", project_dir=pd_override,
                                    manuscript_dir=ms, tex_root=ms, bib="", plan_path=plan_path,
                                    manifest=manifest)
            else:
                reg[name] = _conceptric(name, tex_root, row.get("manifest"), pd_override,
                                        evidence_store)
            prov[name] = "registry-row"
        except ValueError:
            continue    # a malformed data row is skipped, never fatal to the whole registry
    # Standalone exports have an explicit registry. Discovering a historical
    # sibling checkout on the evaluator's host would silently import unrelated
    # projects and violate that boundary.
    if (root / "writing-portability.json").is_file():
        return reg, prov
    # Existing specialized layouts are compatibility fallbacks. Preserve the
    # caller's explicit registry rows, including newly declared empty projects.
    declared_projects = dict(reg)
    # -- compatibility layouts ----------------------------------------------
    reg["paper_eigen"] = Project(
        name="paper_eigen", kind="loop", project_dir="paper_eigen",
        manuscript_dir="paper_eigen/manuscript",
        target_dir="paper_eigen/manuscript",
        loop_dir="paper_eigen/_loop",
        # the P5 collapse of scripts/paper_gates.py (archived 2026-07-08): its
        # banned lists and section count are registry DATA; the one runner is
        # pipeline.loop_gates.run_gates, and the loop dir rides loop_dir above.
        gates_profile={
            "sections": 8,
            "banned_jargon": ["keeper", "spine", "dreamer", "sew-up", "salience",
                              "regrade", "conceptric ledger", "soul"],
            "banned_constructions": [["em-dash", "—"], ["semicolon", "; "],
                                     ["announcement", "in this section"],
                                     ["announcement", "this section "]],
        },
    )
    # paper_falqon: kind flipped "tex" -> "conceptric" (F, 2026-07-11). The old
    # blocker — no corpus registration at all, so a conceptric-kind consumer walking
    # ci.resolve_corpus/corpus_network would get a None tex root — is consumed: the
    # tex_root declared below is "paper_falqon/manuscript" (main.tex lives at that
    # root), so resolve_corpus returns the tex root and corpus_network
    # reconstructs the real graph. The graph itself is no longer just the bare tex
    # walk (13 base leaves): the compiled conceptric (91 nodes / 140 edges) was
    # poured through the validated rewire door into corpus_friction/paper_falqon.jsonl
    # by scripts/pour_conceptric.py, and corpus_network applies it as the overlay —
    # 91 nodes with kinds/essences, 54 dependency edges, the 13-section spine. Flipping
    # kind is now safe because every conceptric-kind consumer resolves to a real tex
    # root AND a real graph. The conceptric-chain fields it owns stay registered.
    reg["paper_falqon"] = Project(
        name="paper_falqon", kind="conceptric", project_dir="paper_falqon",
        tex_root="paper_falqon/manuscript",
        ledger="corpus_friction/paper_falqon.jsonl",
        manuscript_dir="paper_falqon/manuscript",
        plan_path="paper_falqon/manuscript/projection_plan.json",
        target_dir="paper_falqon/manuscript",
        briefs_dir="paper_falqon/manuscript/briefs",
        feedback_ledger="paper_falqon/manuscript/feedback/feedback.jsonl",
        versions_dir="paper_falqon/manuscript/versions",
        evolutions_dir="paper_falqon/manuscript/evolutions",
        bib="paper_falqon/manuscript/refs.bib",
        # the readings stores a validates edge dereferences into (resource_readings /
        # witness_readings): the evidence-coverage gauge's registry door (G3 leg 2).
        evidence_store="paper_falqon/numerics",
    )
    # eigenengine: kind flipped "tex" -> "conceptric" (2026-07-12). Mechanical mirror of the
    # paper_falqon flip (F, 2026-07-11) directly above — not a new author ruling. Grounds:
    # N53 was TIGHTENED by him 2026-07-11 to the calling-card headline ("full chain — grow the
    # conceptric AND converge to a polished document"), its named trigger was "the growth gate
    # opens (falqon proves the chain end-to-end first)", and that trigger fired (FQ6 ran
    # end-to-end, harnessed converge ACCEPTED, paper-falqon-2026-07-11-r1.pdf). This session's
    # plan, whose centerpiece is exactly this registry flip, was his approved plan. Same blocker
    # as falqon, same fix: eigenengine had no corpus registration, so a conceptric-kind consumer
    # walking ci.resolve_corpus/corpus_network got a None tex root. The tex_root declared below
    # is "eigenengine/manuscript" (main.tex lives at that root, no /tex leg, same as falqon),
    # so resolve_corpus returns the tex root and corpus_network reconstructs the
    # real graph: the compiled conceptric (109 nodes / 221 edges, hand-built — see
    # eigenengine/manuscript/conceptric_health.json) poured through the validated rewire door
    # into corpus_friction/eigenengine.jsonl by scripts/pour_conceptric.py, applied by
    # corpus_network as the overlay. The conceptric-chain fields it now owns are registered
    # below, laid out exactly like paper_falqon's block.
    reg["eigenengine"] = Project(
        name="eigenengine", kind="conceptric", project_dir="eigenengine",
        tex_root="eigenengine/manuscript",
        ledger="corpus_friction/eigenengine.jsonl",
        manuscript_dir="eigenengine/manuscript",
        plan_path="eigenengine/manuscript/projection_plan.json",
        target_dir="eigenengine/manuscript",
        briefs_dir="eigenengine/manuscript/briefs",
        feedback_ledger="eigenengine/manuscript/feedback/feedback.jsonl",
        versions_dir="eigenengine/manuscript/versions",
        evolutions_dir="eigenengine/manuscript/evolutions",
        bib="eigenengine/manuscript/refs.bib",
    )
    # paper_roland_qrc: The first foreign artefact registered as a pipeline project. The
    # manuscript is a COLLABORATOR draft (Weiszmüller, Bulancea-Lindvall, Balanov, Zagoskin,
    # Ivády, McCaul — "Dynamical Readout Enrichment for Quantum Reservoir Computing"),
    # mechanically repaired by us at R1; it is not our corpus and never becomes one.
    #
    # kind="conceptric", NOT "tex": the two conceptric-kind consumers are what this project
    # exists for. ``conceptric_projects`` lists ONLY kind="conceptric" rows, and that list is
    # the single place ``corpus_ingest.resolve_corpus`` reads a tex root from — so a "tex" row
    # (ssg-disclosure's family) would be invisible to the viewer roster and to
    # ``corpus_network``, which is exactly the surface the author is meant to read and annotate
    # on. ssg-disclosure is "tex" because it owns NO conceptric and shares its parent's ledger;
    # this project owns a conceptric (147 nodes / 338 edges, poured to its own ledger), so it
    # takes falqon's family, and the pour's own tex-root gate is satisfied either way.
    #
    # The foreign split, and why manuscript_dir != tex_root here (it does not differ for
    # falqon/eigenengine): their tex tree is READ-ONLY to the engine, so tex_root points at
    # ``revision/`` (where main.tex and the compiled main.pdf live — the repaired R1 artefact;
    # ``inputs/`` is the superseded original and is never read), while every engine-side
    # projection — the conceptric, the plan, briefs, versions, and the FEEDBACK LEDGER the
    # author's comments land on — lives under ``paper_roland_qrc/manuscript/``, a directory we
    # own. bib is the revision's refs.bib (three keys added at R1), not inputs'.
    # target_dir is the engine-owned deposit tree (same split): pointing it at revision/
    # made every engine write depend on the plan's meta.target_dir override existing
    # (IDEMPOTENCE row 8; corrected 2026-08-07, WO-20260807-004510-000009).
    reg["paper_roland_qrc"] = Project(
        name="paper_roland_qrc", kind="conceptric", project_dir="paper_roland_qrc",
        tex_root="paper_roland_qrc/revision",
        ledger="corpus_friction/paper_roland_qrc.jsonl",
        manuscript_dir="paper_roland_qrc/manuscript",
        plan_path="paper_roland_qrc/manuscript/projection_plan.json",
        target_dir="paper_roland_qrc/manuscript",
        briefs_dir="paper_roland_qrc/manuscript/briefs",
        feedback_ledger="paper_roland_qrc/manuscript/feedback/feedback.jsonl",
        versions_dir="paper_roland_qrc/manuscript/versions",
        evolutions_dir="paper_roland_qrc/manuscript/evolutions",
        # moved 2026-08-06 (clearing-seam job 2): the R2 gate must resolve refs[]
        # against the VERIFIED merged bib (revision/refs.bib's 73 R1 keys union
        # rewrite/lit/additions.bib's 32 audited R2 keys, LIT_REPORT.md's
        # corrections applied) -- revision/refs.bib itself stays read-only and
        # is one of the two inputs the merge is built from, never edited here.
        bib="paper_roland_qrc/manuscript/refs.bib",
        # the readings store the conceptric's validates edges dereference into: our own
        # independent numerics (single_qubit_repro's verdict table, two_qubit_fix's A/B/C
        # phases), which is what makes the evidence axis real on a foreign artefact.
        evidence_store="paper_roland_qrc/numerics",
        # The marriage law's first leg. display_name is the artefact's OWN title as its
        # authors gave it — not an invented name, so the cockpit leg carries no fiction.
        # Default axis structural: the tex root belongs to the collaborators, so the
        # conceptric declaration is the fold every engine surface routes through.
        manifest={
            "display_name": "Dynamical Readout Enrichment for Quantum Reservoir Computing",
            "ledger": "corpus_friction/paper_roland_qrc.jsonl",
            "projection": "paper_roland_qrc/revision/main.pdf",
            "state": "paper_roland_qrc/manuscript/STATE.json",
            "default_axis": "structural",
            "maps": {
                "structural": "paper_roland_qrc/manuscript/conceptric_v1.json",
                "evidence": "paper_roland_qrc/numerics/single_qubit_repro/REPRO_REPORT.md",
            },
        },
    )
    # A CHILD PROJECT of subset-sum-itqde: the SSG invention disclosure. It is a
    # bare-tex artefact (kind="tex", finalised straight through release.finalize),
    # but unlike eigenengine/paper_falqon it does NOT own a conceptric ledger -
    # it SHARES the subset-sum-itqde corpus BY PROVENANCE. tex_root and ledger
    # point at the parent's substrate (the provenance key), so the disclosure is
    # a projection of the same conceptric to a different purpose, not a new
    # corpus. Its whole technical backing is taken by reference from the
    # whitepaper, so its bib is the whitepaper's reference store.
    # THE WEBSITE (F6, ruled 2026-07-11): the author's public site, a SIBLING repo
    # (phujck.github.io -> gmccaul.co.uk), registered as its own engine project -
    # its substrate is his public identity, not one paper's conceptric, so it is a
    # new kind ("site"), not a child. external_root makes every content path
    # resolve under the sibling clone; the friction ledger stays ENGINE-side
    # (corpus_friction/website.jsonl - the _ENGINE_SIDE rule in path()), so site
    # noise has its own L1 without leaving the drain's home. feedback_ledger is
    # DELIBERATELY empty: a non-empty one would make the engine drain DELEGATE
    # owning_layer=="website" frictions onto it instead of drafting them
    # (friction_consumer._corpus_project); the website demo's visitor-feedback
    # intake is a separate channel, not this field. Deploy is render -> gates ->
    # commit -> HIS push (push-is-human, standing custody posture).
    reg["website"] = Project(
        name="website", kind="site",
        external_root="../phujck.github.io",
        project_dir=".",
        ledger="corpus_friction/website.jsonl",
        manuscript_dir=".",
        target_dir=".",
    )
    reg["ssg-disclosure"] = Project(
        name="ssg-disclosure", kind="tex",
        project_dir="synthetics papers/subset-sum-itqde/disclosure",
        # SHARED corpus tex root: the same literal the subset-sum-itqde data row
        # carries. Read off the hardcoded corpus dict until it was deleted (2026-08-04);
        # inlined rather than resolved from the row because this block is built DURING
        # the merge that produces that row — reading it back here would make the
        # registry depend on its own half-built state.
        tex_root="synthetics papers/subset-sum-itqde/manuscript/tex",
        ledger="corpus_friction/subset-sum-itqde.jsonl",  # SHARED L1 (no own ledger)
        manuscript_dir="synthetics papers/subset-sum-itqde/disclosure",
        target_dir="synthetics papers/subset-sum-itqde/disclosure",
        bib="synthetics papers/subset-sum-itqde/manuscript/whitepaper/references.bib",
    )
    # A compatibility record exists only where its own content home exists.
    # Never inject the deployed checkout's projects into an unrelated root,
    # and never replace an explicitly declared same-name local project.
    for _hand in ("paper_eigen", "eigenengine", "paper_falqon", "paper_roland_qrc",
                  "website", "ssg-disclosure"):
        if _hand in declared_projects:
            reg[_hand] = declared_projects[_hand]
            prov[_hand] = "registry-row"
            continue
        candidate = reg[_hand]
        home = root / (candidate.external_root or candidate.project_dir)
        if not (candidate.external_root or candidate.project_dir) or not home.is_dir():
            reg.pop(_hand, None)
            prov.pop(_hand, None)
            continue
        prov[_hand] = "hardcoded-block"
    return reg, prov


def _projects(repo_root: Path | str | None = None) -> dict[str, Project]:
    """The registry, built fresh per call (it is tiny; no cache to stale)."""
    return _build_registry(Path(repo_root) if repo_root is not None else _repo_root())[0]


def conceptric_projects(repo_root: Path | str | None = None) -> list[dict]:
    """The one authoritative list of every registered project (W-growth G0). One row
    per name — ``{name, kind, tex_root, provenance}`` — where ``provenance`` names the
    layer that defines the winning record (``hardcoded-block`` | ``registry-row``,
    see :func:`_build_registry`). This is the single list
    :func:`corpus_ingest.resolve_corpus` reads a tex root from, so a dashboard-
    scaffolded data-row project is no longer invisible to the conceptric read path (the
    crank's finding, CRANK_RECORD_2026-07-15.json). Built from the same
    :func:`_build_registry` merge every other door walks — never a fourth source.

    Only ``kind="conceptric"`` rows are listed: the read path atomises a conceptric tex
    tree, and a data row is always conceptric, so the finished papers plus every
    scaffolded project appear while the non-conceptric layouts (``site``/``loop``/``tex``
    — e.g. ssg-disclosure, whose tex root is the subset-sum corpus it shares) stay out,
    so ``resolve_corpus`` returns exactly what it did before for those names."""
    reg, prov = _build_registry(Path(repo_root) if repo_root is not None else _repo_root())
    return [{"name": n, "kind": p.kind, "tex_root": p.tex_root,
             "provenance": prov[n]} for n, p in reg.items() if p.kind == "conceptric"]


def resolve(name: str, repo_root: Path | str | None = None) -> Project | None:
    """The one lookup. Unknown (or path-shaped) names → None, never a guess."""
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    root = Path(repo_root) if repo_root is not None else _repo_root()
    return _projects(root).get(name)


def all_projects(repo_root: Path | str | None = None) -> dict[str, Project]:
    return _projects(repo_root)


def content_owners(target: Path | str, repo_root: Path | str | None = None) -> tuple[str, ...]:
    """The registered project(s) whose MOST SPECIFIC resolved content home contains ``target``.

    Homes resolve through :meth:`Project.content_homes` (``external_root`` honoured), so a sibling-rooted
    website's ``"."`` home never claims the engine checkout, and a project registered inside another
    project's directory owns its own subtree. One name is ownership, none is unowned, and several names
    mean equally specific homes overlap: callers that need custody refuse that ambiguity.
    """
    root = Path(repo_root) if repo_root is not None else _repo_root()
    resolved = Path(target).resolve()
    best, owners = -1, []
    for name, proj in _projects(root).items():
        depth = max((len(home.parts) for home in proj.content_homes(root)
                     if resolved == home or resolved.is_relative_to(home)), default=-1)
        if depth < 0:
            continue
        if depth > best:
            best, owners = depth, [name]
        elif depth == best:
            owners.append(name)
    return tuple(sorted(owners))


#: The passage-comment ledger's place inside a registered manuscript home (correction_origin custody).
COMMENT_FEEDBACK_REL = "feedback/feedback.jsonl"


def comment_feedback_home(name: str, repo_root: Path | str | None = None) -> str:
    """The registered canonical passage-comment ledger of ``name``: a checkout-relative POSIX locator.

    This is the CURRENT-SOURCE comment home, ``<manuscript_dir>/feedback/feedback.jsonl`` of the registered
    record, independent of the selected edition. It is distinct from ``Project.feedback_ledger`` (declared
    pipeline feedback, e.g. a conceptric whitepaper drain) and from ``ProjectContext.feedback_ledger``
    (selected-source intake); neither is silently merged into it. An ``external_root`` project keeps its
    content in a sibling repository, so this checkout holds no comment custody for it and the request is
    refused instead of resolving its ``"."`` manuscript home to the engine root.
    """
    root = Path(repo_root) if repo_root is not None else _repo_root()
    proj = resolve(name, repo_root=root)
    if proj is None or not proj.manuscript_dir:
        raise ValueError("Comment origin requires a registered manuscript feedback home.")
    if proj.external_root:
        raise ValueError("This project's content lives in its external repository; this checkout holds no "
                         "passage-comment feedback custody for it.")
    value = (Path(proj.manuscript_dir) / COMMENT_FEEDBACK_REL).as_posix()
    if _escapes(value) or not (root / value).resolve().is_relative_to(root.resolve()):
        raise ValueError("The registered feedback home is outside this checkout.")
    return value


def set_document(project: str, document: dict, repo_root: Path | str | None = None) -> dict:
    """Persist an explicit manuscript edition on a data-backed registry row.

    This is the registry's write door for a UI edition picker.  It refuses path
    escapes and never manufactures a project row, leaving hand-authored registry
    blocks immutable here.
    """
    if not project or "/" in project or "\\" in project or ".." in project:
        raise ValueError("project must be a registered plain name")
    if not isinstance(document, dict):
        raise ValueError("document must be an object")
    clean = {key: value for key, value in document.items()
             if key in {"root", "edition", "manuscript_dir"} and isinstance(value, str) and value.strip()}
    for key in ("root", "manuscript_dir"):
        if key in clean and _escapes(clean[key]):
            raise ValueError(f"document.{key} escapes the repository")
    if "root" not in clean:
        raise ValueError("document.root is required")
    root = Path(repo_root) if repo_root is not None else _repo_root()
    path = root / DATA_PROJECTS_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"registry data is unreadable: {exc}") from exc
    rows = raw.get("projects") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ValueError("registry projects are not a list")
    row = next((candidate for candidate in rows if isinstance(candidate, dict)
                and candidate.get("name") == project), None)
    if row is None:
        raise KeyError(f"no data-backed project {project!r}")
    manifest = row.setdefault("manifest", {})
    if not isinstance(manifest, dict):
        raise ValueError("project manifest is not an object")
    manifest["document"] = clean
    encoded = json.dumps(raw, ensure_ascii=False, indent=1) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=f".{DATA_PROJECTS_FILE}.", delete=False) as temp:
        temp.write(encoded)
        temp_path = Path(temp.name)
    temp_path.replace(path)
    return dict(clean)


def default_project(repo_root: Path | str | None = None) -> str:
    """The project a surface opens on: LAPLACE_ACTIVE_PROJECT, else the corpus
    whose friction ledger moved most recently (delegates the existing rule)."""
    from laplace.research import corpus_ingest as ci
    return ci.default_corpus(repo_root if repo_root is not None else _repo_root())


# ─────────────────────────────────────────────────────────────────────────────
# The marriage law (2026-07-28). A registry row is not a marriage. Married means
# three legs, each mechanical:
#
#   1. the row carries a LAYOUT MANIFEST — where this project keeps its ledger,
#      its projection and its run-state, plus its maps keyed BY AXIS — and every
#      declared path resolves on disk;
#   2. the project is DEPOSITED in the self-conceptric (a node under its
#      project_dir in the grade-0 index);
#   3. it MOUNTS in the cockpit roster (project_states, the inventory every
#      surface reads) under a ruled display name.
#
# The maps are keyed by axis because there is no one map: the upfold depends on
# the axis clustered along (DESIGN_2026-07-28_the-fibred-upfold §4), so a row
# declares maps per axis and marks one as the default routing section. A single
# GLOBAL layout schema would be the global section the no-global-ledger theorem
# forbids; the manifest is per row — the local-sections repair.

#: the manifest's declared paths: where this project keeps each of the three.
MANIFEST_KEYS = ("ledger", "projection", "state")

#: the self-conceptric's grade-0 index — the deposit leg reads this file.
SELF_INDEX = "SELF_SHARD_INDEX.md"

_SHARD_NAME_RE = re.compile(r"<!--\s*shard name:(.+?) kind:")

#: what counts as a BUILT projection sitting on disk (the truth-layer walk's evidence).
_ARTEFACT_GLOBS = ("*.pdf", "*.html", "main.tex")


def _escapes(rel: str) -> bool:
    p = Path(rel)
    return p.is_absolute() or ".." in p.parts


def manifest_issues(manifest: object) -> list[str]:
    """The manifest's SHAPE errors, one string each; ``[]`` means well-formed. Pure — no
    filesystem read, so a row can be validated where it is written. Path EXISTENCE is the
    marriage leg's business (:func:`married`), not the schema's."""
    if not isinstance(manifest, dict) or not manifest:
        return ["absent"]
    issues: list[str] = []
    for key in MANIFEST_KEYS:
        rel = manifest.get(key)
        if not isinstance(rel, str) or not rel.strip():
            issues.append(f"{key} is not declared")
        elif _escapes(rel):
            issues.append(f"{key} path {rel!r} is absolute or escapes the repo root")
    maps = manifest.get("maps")
    if not isinstance(maps, dict) or not maps:
        issues.append("maps declares no axis (maps: {<axis>: <path>}, at least one)")
    else:
        for axis, rel in maps.items():
            if not isinstance(axis, str) or not axis.strip():
                issues.append(f"an axis key is not a name: {axis!r}")
            elif not isinstance(rel, str) or not rel.strip():
                issues.append(f"maps.{axis} is not a path")
            elif _escapes(rel):
                issues.append(f"maps.{axis} path {rel!r} is absolute or escapes the repo root")
    axis = manifest.get("default_axis")
    if not isinstance(axis, str) or not axis.strip():
        issues.append("default_axis is not declared (one axis is the default routing section)")
    elif isinstance(maps, dict) and axis not in maps:
        issues.append(f"default_axis {axis!r} is not a key of maps")
    dn = manifest.get("display_name")
    if dn is not None and (not isinstance(dn, str) or not dn.strip()):
        issues.append("display_name is declared but empty")
    return issues


def manifest_paths(manifest: dict) -> list[tuple[str, str]]:
    """Every path a manifest declares as ``(label, rel)`` — the three layout legs, then one
    per axis. The order is the order the marriage reports them in."""
    out = [(k, manifest[k]) for k in MANIFEST_KEYS if isinstance(manifest.get(k), str)]
    maps = manifest.get("maps")
    if isinstance(maps, dict):
        out += [(f"maps.{a}", r) for a, r in maps.items() if isinstance(r, str)]
    return out


def display_name(proj: Project) -> str:
    """The name the cockpit mounts this project under: the manifest's ruled display name,
    else the bare registry name. ONE producer — ``project_states`` stamps the roster row
    from here, so the marriage's cockpit leg and the served roster cannot disagree."""
    return (str(proj.manifest.get("display_name") or "").strip() or proj.name)


def _deposited_dirs(repo_root: Path) -> set[str]:
    """Every directory the self-conceptric's grade-0 index holds a node under, in ONE pass
    over ``SELF_SHARD_INDEX.md``. Absent/garbled index → empty set (the deposit leg then
    reports missing for everyone, which is the truth: nothing is deposited)."""
    out: set[str] = set()
    try:
        text = (repo_root / SELF_INDEX).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for m in _SHARD_NAME_RE.finditer(text):
        name = m.group(1).strip()
        while "/" in name:
            name = name.rsplit("/", 1)[0]
            if name in out:
                break
            out.add(name)
    return out


def _missing_legs(proj: Project, root: Path, deposited: set[str]) -> list[str]:
    """The unmet legs for one project — ALL of them, never only the first: a truthful row
    reports everything it lacks. Each string is ``<leg>: <why>``."""
    missing: list[str] = []
    issues = manifest_issues(proj.manifest)
    if issues:
        missing += [f"manifest: {i}" for i in issues]
    else:
        for label, rel in manifest_paths(proj.manifest):
            p = proj.path(rel, root)
            if p is None or not p.exists():
                missing.append(f"manifest: {label} path {rel!r} does not exist")
    pd = (proj.project_dir or "").strip("/")
    if not pd or pd == ".":
        missing.append("deposit: the row declares no project_dir to look for")
    elif pd not in deposited:
        missing.append(f"deposit: no node under {pd!r} in {SELF_INDEX}")
    if not str(proj.manifest.get("display_name") or "").strip():
        missing.append("cockpit: no ruled display name (the roster mounts the bare registry name)")
    return missing


def married(project: str | Project, repo_root: Path | str | None = None) -> tuple[bool, list[str]]:
    """The marriage check: ``(married, missing)`` for one project. ``missing`` names every
    unmet leg as ``<leg>: <why>``; an unknown name is not married and says so."""
    root = Path(repo_root) if repo_root is not None else _repo_root()
    proj = project if isinstance(project, Project) else _projects(root).get(project)
    if proj is None:
        return False, [f"registry: no row named {project!r}"]
    missing = _missing_legs(proj, root, _deposited_dirs(root))
    return (not missing), missing


def marriage_roster(repo_root: Path | str | None = None) -> list[dict]:
    """Every registered project's marriage, one row: ``{name, display_name, married,
    missing, legs_missing}``. ``legs_missing`` is the bare leg names (manifest / deposit /
    cockpit) — what the wake prints; ``missing`` carries the reasons. The self-conceptric
    index is read ONCE for the whole roster."""
    root = Path(repo_root) if repo_root is not None else _repo_root()
    deposited = _deposited_dirs(root)
    rows = []
    for name, proj in _projects(root).items():
        missing = _missing_legs(proj, root, deposited)
        rows.append({
            "name": name,
            "display_name": display_name(proj),
            "married": not missing,
            "missing": missing,
            "legs_missing": sorted({m.split(":", 1)[0] for m in missing}),
        })
    return rows


def _holds_artefact(p: Path | None) -> bool:
    if p is None:
        return False
    if p.is_file():
        return True
    if not p.is_dir():
        return False
    return any(next(p.glob(g), None) is not None for g in _ARTEFACT_GLOBS)


def _is_serving_stub(p: Path | None) -> bool:
    """A projection dir whose ONLY artefact is a stub ``main.tex`` -- the serving-gate
    pattern four registered corpora ride (an ~8-line tex whose one job is satisfying
    ``resolve_corpus``; design_conceptric's stub says so verbatim). Form-based, never
    comment-matched: small and structureless (no sectioning/input) IS the stub, so the
    truth layer stops reading a serving gate as a built projection (the 2026-08-23
    finding: a freshly landed stub minted a false conflict, and a second project's
    stub had been minting the same one all along). A dir holding ANY other artefact --
    a built whitepaper is the live counter-case -- stays a projection."""
    if p is None or not p.is_dir():
        return False
    files = [f for g in _ARTEFACT_GLOBS for f in p.glob(g)]
    if len(files) != 1 or files[0].name != "main.tex":
        return False
    try:
        body = files[0].read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return len(body) <= 4096 and not re.search(r"\\(section|chapter|input|include)\b", body)


def _layout_dirs(proj: Project, root: Path) -> tuple[Path | None, Path | None]:
    """``(target_dir, manuscript_dir)`` resolved the way :func:`project_context` resolves
    them — the two roots :func:`_release_state` reads the release sidecar from."""
    md = proj.path(proj.manuscript_dir, root) if proj.manuscript_dir else None
    td = proj.resolved_target_dir(root)
    if td is None and proj.target_dir:
        td = proj.path(proj.target_dir, root)
    return td, md


def truth_layer_check(repo_root: Path | str | None = None) -> list[dict]:
    """One truth per project (PRM-20260721-truth-layer), walked mechanically now that the
    manifest declares where each project keeps its projection and its run-state. Flags a row
    whose surfaces disagree about whether the project has run: a built projection sitting on
    disk while the release machine reads NEVER_RUN, or a second run-state file declared where
    the release machine never wrote a sidecar. One row per contradicted project,
    ``{name, state, why: [...]}``; agreeing projects return nothing.

    The live case this was built on: /storyboard/run said NEVER_RUN beside a minted release."""
    root = Path(repo_root) if repo_root is not None else _repo_root()
    rows: list[dict] = []
    for name, proj in _projects(root).items():
        man = proj.manifest
        if not isinstance(man, dict) or not man:
            continue        # no manifest, no declared surfaces to disagree
        td, md = _layout_dirs(proj, root)
        base, state = _release_state(td, md)
        if state != "NEVER_RUN":
            continue        # the release machine has touched it; its state is the state
        if _publication_release_state(proj, root) is not None:
            continue        # released through the publication door; that IS the run-state
        why: list[str] = []
        rel_proj = man.get("projection")
        if (isinstance(rel_proj, str) and _holds_artefact(proj.path(rel_proj, root))
                and not _is_serving_stub(proj.path(rel_proj, root))):
            why.append(f"a built projection sits at {rel_proj} while the release machine "
                       f"reads NEVER_RUN")
        rel_state = man.get("state")
        if base is None and isinstance(rel_state, str):
            p = proj.path(rel_state, root)
            if p is not None and p.exists():
                # only a declared file whose state value rides the RELEASE ladder is a
                # competing run-state claim; a growth sidecar (SEEDED/…/READY) or any other
                # ladder is a different machine, not a second home (reconciliation
                # 2026-08-07: a project's growth.json, or a bespoke STATE.json on a
                # non-release ladder, is not a release claim). An unparseable file stays
                # flagged — it cannot prove it is not one.
                from laplace.pipeline import release
                declared = None
                parse_failed = False
                try:
                    declared = (json.loads(p.read_text(encoding="utf-8")) or {}).get("state")
                except (OSError, json.JSONDecodeError):
                    parse_failed = True
                if parse_failed or (isinstance(declared, str) and declared in release.STATES):
                    why.append(f"run-state is declared at {rel_state} (which exists) while "
                               f"the release machine has no sidecar — two run-state homes")
        if why:
            rows.append({"name": name, "state": state, "why": why})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# THE one Server-canonical project context (W0.3). Before this, three roots
# competed for one project — the registered ``tex_root`` (``manuscript/tex``, the
# atomiser's source root, a STUB for a PDF-sourced corpus), the registered
# ``manuscript_dir``, and ``resolved_target_dir`` (``manuscript/whitepaper``, where
# the compiled artefact + release + harnessed rounds really live). Different
# consumers walked different roots, so /projection opened the tex stub while
# /review showed the whitepaper PDF (the paper vanished between nav clicks) and the
# version rail walked the manuscript dir and MISSED the harnessed rounds + release.
#
# ``ProjectContext`` resolves every root ONCE, deterministically, and computes THE
# single current-artefact fact. ``resolved_target_dir`` is the authored target
# (plan.meta.target_dir, else the registered convention) — release + rounds resolve
# UNDER it; ``versions`` + ``judge_rounds`` resolve under the manuscript dir (that is
# where they really live — verified on disk for subset-sum-itqde). ``tex_root`` is
# kept as the atomiser source root a corpus not yet projected to its target still
# resolves its artefact from (the documented pre-projection fallback).

#: a minted, named release PDF: ``<slug>-Yyyy-mm-dd-rN.pdf`` (finalize's naming), with the parts named so the
#: newest can be ordered by (date, revision); ``.match`` is the same whether or not a caller reads the parts.
MINTED_PDF_RE = re.compile(r"(?P<slug>.+)-(?P<date>\d{4}-\d{2}-\d{2})-r(?P<rev>\d+)\.pdf$")

#: release states at/after CANDIDATE_LOCKED and before RELEASED — the candidate is
#: lock-clean (candidate_lock.lock_eligible gated the compile), so the current
#: artefact reads ``clean`` there; below the lock it is a working ``candidate`` and
#: RELEASED is its own ``release`` kind. Derived from release.STATES, not restated.
_CLEAN_STATES = frozenset({"CANDIDATE_LOCKED", "AUTHOR_REVIEWED", "FINAL_CLEAN_BUILD",
                           "FINAL_GATES_PASSED", "AUTHOR_ACCEPTED"})

#: the next author/engine gesture a release state invites — the dashboard's
#: ``next_action``, DERIVED from the state and NEVER a fired action (offer-never-fire:
#: naming the gesture is not making it).
_NEXT_ACTION = {
    "NEVER_RUN": "run pipeline", "STAGED": "run pipeline", "WELDED": "converge",
    "MECHANICALLY_VALID": "converge", "UNDER_CONVERGENCE": "review candidate",
    "CANDIDATE_LOCKED": "author review", "AUTHOR_REVIEWED": "final build",
    "FINAL_CLEAN_BUILD": "final gates", "FINAL_GATES_PASSED": "accept",
    "AUTHOR_ACCEPTED": "release", "RELEASED": "released", "REOPENED": "re-converge",
}


@dataclass(frozen=True)
class ProjectContext:
    """One project, fully resolved to absolute paths + the single current-artefact
    fact. Every field is a ``Path`` (absolute, resolved) or ``None`` when the project
    declares no such leg; ``current_artefact`` is the one server-computed
    ``{pdf, tex, version_id, kind}`` fact (paths repo-relative POSIX, declared nulls
    when absent) that every surface consumes instead of re-deriving its own root."""

    name: str
    kind: str
    manuscript_dir: Path | None
    target_dir: Path | None                 # resolved_target_dir (plan override honoured)
    tex_root: Path | None                   # the registered source root (atomiser input)
    release_dir: Path | None                # under target_dir
    rounds_dir: Path | None                 # under target_dir
    versions_dir: Path | None               # under manuscript_dir
    judge_rounds_dir: Path | None           # under manuscript_dir
    feedback_ledger: Path | None
    plan_path: Path | None
    current_artefact: dict                  # {pdf, tex, version_id, kind}
    pipeline_feedback_ledger: Path | None = None  # declared pipeline scope, never silently merged
    storage_dir: Path | None = None         # selected editable/engine-owned receipts home
    comment_feedback_ledger: Path | None = None  # registered passage-comment custody (comment_feedback_home)


def _relposix_or_abs(p: Path | None, root: Path) -> str | None:
    """A repo-relative POSIX path (the current-artefact contract) when ``p`` sits
    under ``root``, else the absolute string (a sibling/external path — never a
    silent lie), ``None`` for ``None``."""
    if p is None:
        return None
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(p)


def _artefact_root(target_dir: Path | None, tex_root: Path | None) -> Path | None:
    """The dir the current artefact lives in: the resolved ``target_dir`` when it
    holds a build (main.pdf or main.tex), else the ``tex_root`` (a corpus not yet
    projected to its target still resolves its artefact from its registered source
    root — the documented pre-projection fallback), else ``None``."""
    for cand in (target_dir, tex_root):
        if cand is not None and ((cand / "main.pdf").is_file() or (cand / "main.tex").is_file()):
            return cand
    return None


def _newest_minted_pdf(base: Path) -> Path | None:
    minted = sorted((p for p in base.glob("*.pdf") if MINTED_PDF_RE.match(p.name)),
                    key=lambda p: (p.name, _safe_mtime(p)))
    return minted[-1] if minted else None


def _safe_mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _current_artefact(target_dir: Path | None, tex_root: Path | None,
                      state: str, root: Path) -> dict:
    """THE single server-computed current-artefact fact ``{pdf, tex, version_id,
    kind}``. Resolution order:

      1. RELEASED  → the minted final PDF (finalize.json's ``pdf_path``, else the
                     newest ``*-yyyy-mm-dd-rN.pdf`` under the target dir), kind
                     ``release``;
      2. else      → the working candidate at the artefact root: ``main.pdf`` (else
                     the newest minted PDF beside it) + ``main.tex``, kind ``clean``
                     when the release is lock-clean else ``candidate``;
      3. declared nulls when neither the target nor the tex root holds an artefact.

    Paths are repo-relative POSIX. The tex-stub is NEVER consulted when the target
    dir holds the real build (the two-root repair: for subset-sum-itqde the target
    ``whitepaper/main.pdf`` wins and ``tex/main.tex`` — the 35-line stub — is never
    reached)."""
    empty = {"pdf": None, "tex": None, "version_id": None, "kind": None}
    base = _artefact_root(target_dir, tex_root)
    if base is None:
        return empty
    tex = base / "main.tex"
    tex = tex if tex.is_file() else None

    if state == "RELEASED":
        pdf_base = target_dir if target_dir is not None else base
        rel_pdf = None
        fin = pdf_base / "release" / "finalize.json"
        if fin.is_file():
            try:
                rel_pdf = (json.loads(fin.read_text(encoding="utf-8")) or {}).get("pdf_path")
            except (OSError, json.JSONDecodeError):
                rel_pdf = None
        pdf = (pdf_base / rel_pdf) if (rel_pdf and (pdf_base / rel_pdf).is_file()) else None
        if pdf is None:
            pdf = _newest_minted_pdf(pdf_base)
        return {"pdf": _relposix_or_abs(pdf, root), "tex": _relposix_or_abs(tex, root),
                "version_id": (pdf.stem if pdf is not None else None), "kind": "release"}

    main_pdf = base / "main.pdf"
    version_id = None
    if main_pdf.is_file():
        pdf = main_pdf
    else:
        pdf = _newest_minted_pdf(base)          # a candidate with no fresh main.pdf yet
        version_id = pdf.stem if pdf is not None else None
    return {"pdf": _relposix_or_abs(pdf, root), "tex": _relposix_or_abs(tex, root),
            "version_id": version_id,
            "kind": ("clean" if state in _CLEAN_STATES else "candidate")}


def _publication_release_state(proj: Project, root: Path) -> tuple[str, str | None] | None:
    """A release recorded through the PUBLICATION door: the manifest-declared state file
    parses as schema ``eigenengine.featured-generation-release.v*`` with ``status: live``.
    Returns ``("RELEASED", updated_iso)`` or ``None``. The live case this reader exists
    for: feedback-twinning-fields released through the website manifest (byte-verified
    sha256s, a live pages deploy) and never rode ``release.transition``, so the sidecar
    reader called it NEVER_RUN beside a released paper (truth-layer reconciliation
    2026-08-07)."""
    man = proj.manifest if isinstance(proj.manifest, dict) else None
    rel_state = man.get("state") if man else None
    if not isinstance(rel_state, str):
        return None
    p = proj.path(rel_state, root)
    if p is None or not p.is_file():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return None
    if (str(doc.get("schema", "")).startswith("eigenengine.featured-generation-release.")
            and doc.get("status") == "live"):
        return "RELEASED", (doc.get("revised_at") or doc.get("released_at"))
    return None


def _release_state(target_dir: Path | None, manuscript_dir: Path | None) -> tuple[Path | None, str]:
    """The release state read TARGET-FIRST then manuscript (the canonical location is
    ``<target>/release/state.json`` — where the release machine writes; the manuscript
    dir is the fallback for a project whose target IS the manuscript). Returns
    ``(base_dir_where_found, state)``; ``(None, "NEVER_RUN")`` when no sidecar exists
    — NEVER_RUN is distinct from the ``STAGED`` default ``current_state`` returns on
    absence (the release machine has never touched this project)."""
    from laplace.pipeline import release
    for base in (target_dir, manuscript_dir):
        if base is not None and (base / "release" / "state.json").is_file():
            try:
                return base, release.current_state(base)
            except Exception:  # noqa: BLE001 — a corrupt sidecar degrades, never crashes the roster
                return base, "STAGED"
    return None, "NEVER_RUN"


def project_context(name: str, repo_root: Path | None = None) -> ProjectContext | None:
    """THE one fully-resolved context for a registered project (name), or ``None`` for
    an unknown / path-shaped name (the :func:`resolve` fence). Every root resolved
    once; the current artefact computed once. This is the door /projection,
    /review, the version rail, and the dashboard all resolve their project through —
    so they can never disagree about where the paper is."""
    root = Path(repo_root or _repo_root()).resolve()
    proj = resolve(name, repo_root=root)
    if proj is None:
        return None
    md = proj.path(proj.manuscript_dir, root) if proj.manuscript_dir else None
    td = proj.resolved_target_dir(root)
    if td is None and proj.target_dir:
        td = proj.path(proj.target_dir, root)
    tex_root = proj.path(proj.tex_root, root) if proj.tex_root else None
    release_dir = (td / "release") if td is not None else None
    rounds_dir = (td / "rounds") if td is not None else None
    versions_dir = (proj.path(proj.versions_dir, root) if proj.versions_dir
                    else (md / "versions" if md is not None else None))
    judge_rounds_dir = (md / "judge_rounds") if md is not None else None
    pipeline_feedback_ledger = proj.path(proj.feedback_ledger, root) if proj.feedback_ledger else None
    plan_path = proj.plan(root)
    _base, state = _release_state(td, md)
    art = _current_artefact(td, tex_root, state, root)
    # The walk, source editor and PDF door must describe the selected edition.
    # A registered empty target must not hide a substantive selected manuscript.
    from laplace.manuscript import manuscript_source
    selected = manuscript_source.resolve(proj.name, repo_root=root)
    feedback_ledger = manuscript_source.feedback_ledger(proj.name, root, source=selected)
    try:
        comment_feedback_ledger = root / comment_feedback_home(proj.name, root)
    except ValueError:
        comment_feedback_ledger = None
    if selected.get("status") == "resolved" and selected.get("root"):
        source_file = root / selected["root"]
        if art.get("tex") != selected["root"]:
            pdf_file = source_file.with_suffix(".pdf")
            art = {"tex": selected["root"],
                   "pdf": _relposix_or_abs(pdf_file, root) if pdf_file.is_file() else None,
                   "version_id": None, "kind": "candidate"}
        art["source_revision"] = selected.get("revision")
        art["edition"] = selected.get("edition")
    return ProjectContext(
        name=proj.name, kind=proj.kind, manuscript_dir=md, target_dir=td,
        tex_root=tex_root, release_dir=release_dir, rounds_dir=rounds_dir,
        versions_dir=versions_dir, judge_rounds_dir=judge_rounds_dir,
        feedback_ledger=feedback_ledger, plan_path=plan_path, current_artefact=art,
        pipeline_feedback_ledger=pipeline_feedback_ledger,
        storage_dir=manuscript_source.storage_home(proj.name, root, source=selected),
        comment_feedback_ledger=comment_feedback_ledger)


def project_states(repo_root: Path | None = None) -> list[dict]:
    """Per-project release convergence state, the inventory authority: one row per
    registered project, ``{name, kind, display_name, state, updated, rounds_n,
    pipeline_position, latest_artefact, staleness, next_action}``.

    ``state`` / ``pipeline_position`` is ``release.current_state`` when the sidecar FILE
    exists (read TARGET-FIRST, since the release machine writes ``<target>/release/`` —
    the whitepaper for subset-sum, not the manuscript dir the old roster walked, which
    read the paper as NEVER_RUN), else ``"NEVER_RUN"`` — distinct from the ``"STAGED"``
    default ``current_state`` returns on absence. A corrupt sidecar warns (never crashes
    the roster). ``rounds_n`` counts the harnessed mech rounds (target-first) PLUS the
    ``judge_rounds/*round*.json`` layout (manuscript-side) — otherwise a project whose
    rounds live under the target dir (subset-sum) reads the wrong count.

    The dashboard enrichers, all budget-conscious pure reads: ``latest_artefact`` is
    the one current-artefact fact (:func:`project_context`); ``next_action`` is the
    gesture the state invites (offer-never-fire). ``staleness`` is plainly
    ``"unchecked"`` here — the per-corpus staleness reads (nodemap / plan→prose) are
    not cheap to run per row across the whole roster, so the roster names the gap
    rather than paying it or faking a verdict. ``open_decisions`` is likewise omitted,
    not faked: the desk join is heavy and this roster stays a cheap inventory read.
    """
    root = repo_root or _repo_root()
    rows: list[dict] = []
    for name, proj in all_projects().items():
        ctx = project_context(name, root)
        md = ctx.manuscript_dir if ctx is not None else (
            proj.path(proj.manuscript_dir, root) if proj.manuscript_dir else None)
        td = ctx.target_dir if ctx is not None else None

        # the release state — TARGET-FIRST, then the manuscript dir (the two-root repair).
        state, updated = "NEVER_RUN", None
        base = None
        for cand in (td, md):
            if cand is not None and (cand / "release" / "state.json").is_file():
                base = cand
                break
        if base is not None:
            from laplace.pipeline import release
            state_file = base / "release" / "state.json"
            try:
                state = release.current_state(base)
                updated = (json.loads(state_file.read_text(encoding="utf-8")) or {}).get("updated")
            except (OSError, json.JSONDecodeError) as e:
                logging.warning(
                    "registry: state.json for project %r exists but is unparseable: %s", name, e)
                state = "STAGED"
        else:
            pub = _publication_release_state(proj, root)
            if pub is not None:
                state, updated = pub

        # harnessed mech rounds (target-first), PLUS the judge_rounds layout (manuscript-side).
        rounds_n = 0
        for cand in (td, md):
            if cand is not None and (cand / "rounds" / "harnessed").is_dir():
                rounds_n = sum(1 for _ in (cand / "rounds" / "harnessed").glob("mech_r*.json"))
                break
        for jr in ((ctx.judge_rounds_dir if ctx is not None else None),
                   (md.parent / "judge_rounds" if md is not None else None)):
            if jr is not None and jr.is_dir():
                rounds_n += sum(1 for _ in jr.glob("*round*.json"))
                break

        artefact = ctx.current_artefact if ctx is not None else {
            "pdf": None, "tex": None, "version_id": None, "kind": None}
        rows.append({
            "name": name, "kind": proj.kind, "state": state,
            # the name the cockpit mounts this row under (the marriage law's third leg):
            # the manifest's ruled display name, else the bare registry name.
            "display_name": display_name(proj),
            "updated": updated, "rounds_n": rounds_n,
            "pipeline_position": state,
            "latest_artefact": artefact,
            "staleness": "unchecked",
            "next_action": _NEXT_ACTION.get(state, "review candidate"),
        })
    return rows


def plan_path_for(corpus: str, repo_root: Path | str | None = None) -> Path | None:
    """The projection plan for a corpus, located through the one project registry
    (this module, the one door).
    Unknown corpus names (including traversal shapes) never reach the filesystem,
    and a registered project without a plan (paper_eigen, eigenengine) is None."""
    root = Path(repo_root).resolve() if repo_root is not None else _repo_root().resolve()
    proj = resolve(corpus, repo_root=root)
    if proj is None or not proj.plan_path:
        return None
    p = proj.plan(root)
    p = p.resolve() if p is not None else None
    if p is None:
        return None
    try:
        p.relative_to(root)          # containment: the registry should guarantee this,
    except ValueError:               # but the fence is checked, not assumed
        return None
    return p if p.is_file() else None
