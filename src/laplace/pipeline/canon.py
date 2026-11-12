"""Canon loader, ``canon://`` resolver, and relevance selection.

The canon is the single source of truth: a wiki (knowledge graph of aesthetics,
operations, structure, workflow, and domain axioms) plus skills (protocol specs
with optional backing scripts) plus agent personas, indexed by ``index.yaml``.

The loader DISCOVERS files on disk and OVERLAYS the manifest metadata. Anything
missing from the manifest falls back to a sensible default, so the canon still
works if the manifest drifts. The manifest is the mutable record the assessment
and dreamer layers write back to (skill ``status`` and ``fitness``).
"""

from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Locating the canon
# ---------------------------------------------------------------------------

# Packaged default: the canon shipped inside this package.
_PACKAGED_CANON = Path(__file__).resolve().parent / "canon"


def _dashboard_domain(proj: Any) -> str:
    """Routing label for a registry project on the dashboard (the demotion: index.yaml's domains:
    is routing-only). The site rides ``web``, synthetics-papers projects ride ``synthetics``, the
    rest are engine-side. A missing project (roster/registry mismatch) has no label."""
    if proj is None:
        return ""
    if getattr(proj, "kind", "") == "site":
        return "web"
    if (getattr(proj, "project_dir", "") or "").startswith("synthetics papers/"):
        return "synthetics"
    return "engine"


def canon_root() -> Path:
    """Return the active canon directory.

    Override with ``LAPLACE_CANON`` to point every LLM at a shared working copy
    (the dreamer commits there). Defaults to the canon packaged with mcp-gerard.
    """
    env = os.environ.get("LAPLACE_CANON")
    if env:
        return Path(env).expanduser()
    return _PACKAGED_CANON


# The transient Windows os.replace window. The canon read path is lock-free by
# design (orient/assess/skill never take the canon write lock - locking.py), so a
# reader can race the dreamer's atomic swap of lifecycle.yaml (dreamer._save_lifecycle
# does mkstemp + os.replace). On POSIX os.replace is fully atomic and a concurrent
# open never fails. On Windows it briefly holds an exclusive handle on the
# destination (CPython opens the temp without FILE_SHARE_DELETE), so for the instant
# of the swap a lock-free open can fail with PermissionError (a sharing violation) or
# momentary FileNotFoundError. Neither is a torn read - both are sub-millisecond - so
# a tiny bounded retry rides over them. This is the read-side conjugate of the
# write-side retry the dreamer already does on os.replace; together they cover both
# ends of the swap window. The budget (~100ms) is only ever spent during an actual
# concurrent swap and stays far inside the tool watchdog.
_REPLACE_RETRY_ATTEMPTS = 50
_REPLACE_RETRY_DELAY = 0.002


def _read_text_lockfree(path: Path, encoding: str = "utf-8") -> str:
    """Read a file a writer may be atomically swapping in via ``os.replace``.

    Retries briefly on the transient ``PermissionError``/``FileNotFoundError`` a
    lock-free reader sees during the Windows ``os.replace`` window, then re-raises
    if it persists past the bounded budget (a real, non-transient problem rather
    than a sub-millisecond swap collision)."""
    for attempt in range(_REPLACE_RETRY_ATTEMPTS):
        try:
            return path.read_text(encoding=encoding)
        except (PermissionError, FileNotFoundError):
            if attempt == _REPLACE_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_RETRY_DELAY)
    raise AssertionError("unreachable: the loop returns or raises")  # pragma: no cover


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_EXPERIMENTAL_RE = re.compile(r"\[EXPERIMENTAL\]", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+")

# Provenance baseline. The canon was grown across prior sessions in an ad-hoc
# way - neither deliberately hand-authored as one piece nor engine-generated with
# a recorded origin. So a node with no recorded provenance is tagged "ancestor":
# inherited from something older, trusted by default but flagged for examination
# when it conflicts or stops functioning. It is between "do not touch" and "do
# not trust". A node the engine generates going forward records its real origin
# (generated_by), so a genuinely empty source then means a writer failed to stamp
# - a real defect, not the baseline.
ANCESTOR = "ancestor"


def _skill_source(overlay: dict[str, Any], life: dict[str, Any]) -> str:
    """Resolve a skill's provenance door.

    A hand-set manifest ``source`` wins (the deliberate record). Else the
    machine's own forge trail: an explicit ``generated_by`` the dreamer stamps,
    or a bare ``forged`` timestamp (the older forge records carry no
    ``generated_by``, but a forged skill is the dreamer's by definition). Else
    the ad-hoc baseline, ``ancestor``.
    """
    return (
        str(overlay.get("source") or "")
        or str(life.get("generated_by") or "")
        or ("dreamer" if life.get("forged") else "")
        or ANCESTOR
    )


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter dict, body) for a markdown file with YAML frontmatter."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data, text[m.end() :]


_ESSENCE_CAP = 280


def _essence(content: str, cap: int = _ESSENCE_CAP) -> str:
    """The grade-0 digest of a node: its first substantive line of prose, capped.

    A handle carries the essence so a goal can decide whether to descend for the
    full body, without the body riding into every orient - the body-dump that blew
    the context cap. The conjugate, for canon nodes, of the shard's ``essence``
    field: computed on demand, never stored."""
    _fm, body = _split_frontmatter(content)
    for block in body.split("\n\n"):
        line = " ".join(block.split()).lstrip("#").strip()
        if len(line) >= 24:
            return line[:cap] + ("…" if len(line) > cap else "")
    flat = " ".join(body.split())
    return flat[:cap] + ("…" if len(flat) > cap else "")


def _parse_consistency(value: Any) -> list[tuple[str, str, str]]:
    """Parse a frontmatter ``consistency`` annotation into typed check tuples.

    Mirrors the substrate seed grammar: each entry is ``<ref> | <rel> | <note>``,
    where ``rel`` is ``supports`` or ``contradicts`` (default ``supports`` when
    omitted) and the note is free text. Accepts a single string or a list of
    strings. A ``contradicts`` entry is how the canon's own prose declares an
    axiom-level conflict, which ``graph.from_canon`` projects into the edge the
    health guard surfaces - a contradiction being the highest-signal thing it can
    find. ``ref`` is resolved against the canon node index by the projector, so
    it may be a wiki tail, a full ``aesthetics/voice_and_style`` ref, or a skill
    name, exactly as a prose link is.
    """
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[tuple[str, str, str]] = []
    for item in items:
        if not isinstance(item, str):
            continue
        seg = [p.strip() for p in item.split("|")]
        if not seg or not seg[0]:
            continue
        rel = seg[1].lower() if len(seg) > 1 and seg[1] else "supports"
        note = seg[2] if len(seg) > 2 else ""
        out.append((seg[0], rel, note))
    return out


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


def _parse_earned_by(value: Any) -> list[tuple[str, str]]:
    """Parse a frontmatter ``earned_by`` annotation into provenance-down tuples.

    The down-pointer of the both-ways audit (``graph.audit_both_ways``): a global
    node names the *specific occurrence* that earned it, not just the coarse
    ``source`` door. Each entry is ``<occurrence> | <note>``, where ``occurrence``
    is a reference to a concrete artifact that taught the node - a dated session
    handoff (``SESSION_HANDOFF_2026-06-05_*.md``), a soul entry (``soul/0004``), a
    diary date, or a result file - and the note says what about it earned the node.
    Accepts a single string or a list. Unlike ``consistency`` this resolves to an
    *artifact on disk*, not a canon graph node, so it records provenance without
    creating a dangling edge (the occurrence lives outside the canon, the way a
    citation's reference lives outside the manuscript).
    """
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, str):
            continue
        seg = [p.strip() for p in item.split("|")]
        if not seg or not seg[0]:
            continue
        note = seg[1] if len(seg) > 1 else ""
        out.append((seg[0], note))
    return out


@dataclass
class Skill:
    name: str
    description: str
    activity: str  # generating | staging | evaluating
    domain: str
    status: str  # experimental | core | deprecated
    backing: str | None
    tags: list[str]
    path: Path  # the skill directory
    source: str = "ancestor"  # provenance: a generated_by door (dreamer|...) or "ancestor" for the pre-provenance baseline
    link: str = "linked"  # learning state: loose | linked | closed
    consistency: list[tuple[str, str, str]] = field(default_factory=list)  # typed (ref, rel, note) check edges from frontmatter
    earned_by: list[tuple[str, str]] = field(default_factory=list)  # provenance-down: (occurrence, note) - the occurrence that earned this node

    @property
    def skill_md(self) -> Path:
        return self.path / "SKILL.md"

    @property
    def backing_path(self) -> Path | None:
        return self.path / self.backing if self.backing else None

    def search_blob(self) -> set[str]:
        return _tokenize(" ".join([self.name, self.description, *self.tags]))

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "activity": self.activity,
            "domain": self.domain,
            "status": self.status,
            "description": self.description,
            "backing": self.backing,
            "tags": self.tags,
            "source": self.source,
            "link": self.link,
        }


@dataclass
class WikiNode:
    ref: str  # e.g. "aesthetics/voice_and_style"
    title: str
    scope: str  # global | domain
    domain: str | None
    tags: list[str]
    path: Path
    source: str = "ancestor"  # provenance door, or "ancestor" for the pre-provenance baseline
    link: str = "linked"  # learning state: loose | linked | closed
    parent: str | None = None  # coarse node this sits beneath; None = top-level. A node with children is itself coarse.
    consistency: list[tuple[str, str, str]] = field(default_factory=list)  # typed (ref, rel, note) check edges from frontmatter
    earned_by: list[tuple[str, str]] = field(default_factory=list)  # provenance-down: (occurrence, note) - the occurrence that earned this node

    def search_blob(self) -> set[str]:
        return _tokenize(" ".join([self.ref, self.title, *self.tags]))


@dataclass
class Canon:
    root: Path
    manifest: dict[str, Any]
    lifecycle: dict[str, Any] = field(default_factory=dict)
    skills: dict[str, Skill] = field(default_factory=dict)
    wiki: dict[str, WikiNode] = field(default_factory=dict)

    # -- construction -------------------------------------------------------
    @classmethod
    def load(cls, root: Path | None = None) -> Canon:
        root = root or canon_root()
        manifest = cls._load_manifest(root)
        lifecycle = cls._load_lifecycle(root)
        canon = cls(root=root, manifest=manifest, lifecycle=lifecycle)
        canon._discover_skills()
        canon._discover_wiki()
        return canon

    @staticmethod
    def _load_lifecycle(root: Path) -> dict[str, Any]:
        """Machine-owned status/fitness overlay the dreamer writes back to.

        Kept separate from index.yaml so the hand-authored, commented manifest is
        never rewritten by automation.
        """
        path = root / "lifecycle.yaml"
        if not path.exists():
            return {"skills": {}}  # no overlay yet - the fast path, never retried
        try:
            text = _read_text_lockfree(path)
        except FileNotFoundError:
            # Vanished mid-swap after the existence check and never reappeared
            # within the retry budget; treat as "no overlay this load" - the mtime
            # fingerprint triggers a fresh load once the swap settles.
            return {"skills": {}}
        data = yaml.safe_load(text) or {}
        data.setdefault("skills", {})
        return data

    @staticmethod
    def _load_manifest(root: Path) -> dict[str, Any]:
        path = root / "index.yaml"
        empty = {"version": 1, "wiki": {}, "domains": {}, "skills": {}}
        if not path.exists():
            return empty
        try:
            # Lock-free hot read on every get_canon; an editor's atomic-save swaps
            # index.yaml the same way the dreamer swaps lifecycle.yaml, so ride the
            # same Windows os.replace window.
            text = _read_text_lockfree(path)
        except FileNotFoundError:
            return empty
        data = yaml.safe_load(text) or {}
        for key in ("wiki", "domains", "skills"):
            data.setdefault(key, {})
        return data

    def _discover_skills(self) -> None:
        skills_dir = self.root / "skills"
        overlay = self.manifest.get("skills", {})
        if not skills_dir.is_dir():
            return
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            sk_dir = skill_md.parent
            name = sk_dir.name
            text = _read_head(skill_md)
            fm, _ = _split_frontmatter(text)
            o = overlay.get(name, {}) or {}
            description = str(o.get("description") or fm.get("description") or "")
            # status precedence: lifecycle overlay (machine) > manifest > inference.
            life = (self.lifecycle.get("skills", {}) or {}).get(name, {}) or {}
            status = life.get("status") or o.get("status")
            if not status:
                status = "experimental" if _EXPERIMENTAL_RE.search(text[:600]) else "core"
            self.skills[name] = Skill(
                name=name,
                description=description,
                activity=o.get("activity", "staging"),
                domain=o.get("domain", "global"),
                status=status,
                backing=o.get("backing"),
                tags=list(o.get("tags", [])),
                path=sk_dir,
                source=_skill_source(o, life),
                link=str(o.get("link") or "linked"),
                consistency=_parse_consistency(fm.get("consistency")),
                earned_by=_parse_earned_by(fm.get("earned_by")),
            )

    def _discover_wiki(self) -> None:
        wiki_dir = self.root / "wiki"
        overlay = self.manifest.get("wiki", {})
        domains = self.manifest.get("domains", {})
        if not wiki_dir.is_dir():
            return
        # Map domain-owned refs so discovery can scope them correctly.
        domain_of: dict[str, str] = {}
        for dname, dmeta in domains.items():
            if isinstance(dmeta, dict):
                if dmeta.get("axioms"):
                    domain_of[dmeta["axioms"]] = dname
                for pref in (dmeta.get("projects") or {}).values():
                    domain_of[pref] = dname
        for md in sorted(wiki_dir.rglob("*.md")):
            ref = md.relative_to(wiki_dir).as_posix()[: -len(".md")]
            if ref == "index":
                continue  # superseded by index.yaml as the machine router
            o = overlay.get(ref, {}) or {}
            dom = domain_of.get(ref)
            fm, body = _split_frontmatter(_read_head(md))
            title = o.get("title") or _first_heading(body) or ref
            self.wiki[ref] = WikiNode(
                ref=ref,
                title=title,
                scope=o.get("scope", "domain" if dom else "global"),
                domain=dom,
                tags=list(o.get("tags", [])),
                path=md,
                source=str(o.get("source") or "") or ANCESTOR,
                link=str(o.get("link") or "linked"),
                consistency=_parse_consistency(fm.get("consistency")),
                earned_by=_parse_earned_by(fm.get("earned_by")),
            )

        # Cluster wiring (post-pass, once every ref is known): a node nests under
        # an explicit manifest ``parent`` or, failing that, its directory's
        # ``index`` coarse node. This is what lets orient stay scale-local.
        refs = set(self.wiki)
        for ref, node in self.wiki.items():
            explicit = (overlay.get(ref, {}) or {}).get("parent")
            node.parent = explicit if explicit else _derive_parent(ref, refs)

    # -- resolution ---------------------------------------------------------
    def resolve(self, ref: str) -> tuple[Path, str]:
        """Resolve a ``canon://`` / bare ref to (path, content). Raises KeyError."""
        r = ref.strip()
        if r.startswith("canon://"):
            r = r[len("canon://") :]
        r = r.strip("/")
        candidates = [
            self.root / r,
            self.root / f"{r}.md",
            self.root / "wiki" / f"{r}.md",
            self.root / "skills" / r / "SKILL.md",
            self.root / r / "SKILL.md",
        ]
        for c in candidates:
            if c.is_file():
                return c, c.read_text(encoding="utf-8")
        raise KeyError(f"Cannot resolve canon ref: {ref!r}")

    # -- relevance ----------------------------------------------------------
    def domains(self) -> dict[str, Any]:
        return self.manifest.get("domains", {})

    def infer_domain(self, goal: str) -> str | None:
        """Guess the active domain from goal text via domain tags / names."""
        tokens = _tokenize(goal)
        best, best_score = None, 0
        for dname, dmeta in self.domains().items():
            blob = _tokenize(dname + " " + " ".join((dmeta or {}).get("tags", [])))
            score = len(tokens & blob)
            if score > best_score:
                best, best_score = dname, score
        return best

    # Goal tokens that signal a generating intent, even when no generating-
    # skill tag overlaps. When the goal contains at least one of these words
    # and no generating skill makes the natural top-limit cut, the highest-
    # scoring generating skill is promoted into the result set so the orient
    # bundle always offers a generating activity when appropriate.
    _GENERATING_INTENT_TOKENS = frozenset({
        "write", "draft", "generate", "create", "build", "compose",
        "produce", "sketch", "scaffold", "seed", "forge", "author",
    })

    # The blind-generation discipline: when a goal signals generating an
    # artefact, the orchestration protocol (builder != judge: delegate to a
    # blind, context-starved generator whose context the orchestrator
    # architects; judge from outside) MUST surface, regardless of which domain
    # the goal mis-routes to. The pre-commit check (META_TEST_2026-06-05) found
    # "generate a manuscript draft" mis-routed to `talks` and never surfaced
    # this skill - so blindness was *remembered, not enforced*. Pinning the
    # skill by name (not by token overlap, which the mis-route defeats) makes a
    # generate-artefact orient reliably carry the discipline. Held loosely: a
    # rename of the skill is caught by the test that this surfaces.
    _GENERATION_DISCIPLINE_SKILL = "orchestrated_generation"

    def rank_skills(
        self, goal: str, domain: str | None = None, limit: int = 6
    ) -> list[Skill]:
        tokens = _tokenize(goal)
        generating_intent = bool(tokens & self._GENERATING_INTENT_TOKENS)
        scored: list[tuple[float, Skill]] = []
        for sk in self.skills.values():
            if sk.status == "deprecated":
                continue
            score = float(len(tokens & sk.search_blob()))
            if domain and sk.domain == domain:
                score += 2.0
            if sk.domain not in ("global", domain) and sk.domain != "web":
                score -= 1.0  # off-domain skills are less relevant
            if sk.status == "core":
                score += 0.5  # mild prior toward proven tools
            if score > 0:
                scored.append((score, sk))
        scored.sort(key=lambda x: (-x[0], x[1].name))
        top = scored[:limit]

        # When the goal signals creation intent but no generating skill made
        # the cut, promote the highest-scoring non-deprecated generating skill
        # into the result (replacing the lowest-scoring item) so the orient
        # bundle always offers at least one generating activity.
        if generating_intent and not any(sk.activity == "generating" for _, sk in top):
            gen_candidates = [
                (sc, sk) for sc, sk in scored[limit:]
                if sk.activity == "generating"
            ]
            if not gen_candidates:
                # no generating skill scored at all - score them from scratch
                gen_candidates = [
                    (0.0, sk)
                    for sk in self.skills.values()
                    if sk.activity == "generating" and sk.status != "deprecated"
                    and not any(s is sk for _, s in top)
                ]
                gen_candidates.sort(key=lambda x: (x[0], x[1].name))
            if gen_candidates:
                best_gen = gen_candidates[0]
                top = top[: limit - 1] + [best_gen]

        # When the goal signals generating an artefact, pin the blind-generation
        # discipline into the bundle even if domain mis-routing kept it below the
        # cut. It is the protocol that turns "generate" from a builder grading its
        # own build into an orchestrator architecting a blind generator's context
        # - enforced by surfacing, not left to memory (META_TEST_2026-06-05). It
        # rides in alongside the generating skill it governs, not in place of it.
        if generating_intent:
            discipline = self.skills.get(self._GENERATION_DISCIPLINE_SKILL)
            if (
                discipline is not None
                and discipline.status != "deprecated"
                and not any(s is discipline for _, s in top)
            ):
                score = next(
                    (sc for sc, sk in scored if sk is discipline), 0.0
                )
                # Drop the lowest-scoring item that is NOT a generating skill, so
                # the discipline rides alongside the generating skill it governs
                # rather than displacing it (an artefact goal wants both: the
                # generator AND the protocol that keeps it blind).
                drop_idx = next(
                    (i for i in range(len(top) - 1, -1, -1)
                     if top[i][1].activity != "generating"),
                    len(top) - 1,
                )
                top = top[:drop_idx] + top[drop_idx + 1:] + [(score, discipline)]

        return [sk for _, sk in top]

    def rank_wiki(self, goal: str, domain: str | None, limit: int = 4) -> list[WikiNode]:
        tokens = _tokenize(goal)
        scored: list[tuple[int, WikiNode]] = []
        for node in self.wiki.values():
            if node.parent is not None:
                continue  # interior to a cluster - surfaced by descending its coarse node, not here
            if node.scope == "domain" and node.domain != domain:
                continue
            score = len(tokens & node.search_blob())
            if score > 0:
                scored.append((score, node))
        scored.sort(key=lambda x: (-x[0], x[1].ref))
        return [n for _, n in scored[:limit]]

    def domain_nodes(self, domain: str) -> list[WikiNode]:
        """Axioms + active project nodes for a domain, in load order."""
        return [n for n in self.wiki.values() if n.domain == domain]

    def children(self, ref: str) -> list[WikiNode]:
        """The interior of a coarse node: the nodes that nest directly beneath it."""
        return [n for n in self.wiki.values() if n.parent == ref]

    def is_coarse(self, ref: str) -> bool:
        """A node is coarse when something nests beneath it - it stands in for a subgraph."""
        return any(n.parent == ref for n in self.wiki.values())

    def clusters(self) -> dict[str, dict[str, Any]]:
        """The descent map: every coarse node to its direct members. Recursive -
        a member that is itself coarse is flagged, so a reader descends level by
        level instead of receiving the whole tree at once."""
        out: dict[str, dict[str, Any]] = {}
        for n in self.wiki.values():
            kids = self.children(n.ref)
            if kids:
                out[f"canon://{n.ref}"] = {
                    "title": n.title,
                    "members": [
                        {"ref": f"canon://{k.ref}", "title": k.title, "coarse": self.is_coarse(k.ref)}
                        for k in kids
                    ],
                }
        return out

    def global_foundation(self) -> list[WikiNode]:
        """Top-level global nodes only. A coarse node stands in for its cluster,
        so the interior (any node with a ``parent``) is reached by descending,
        never flattened into the foundation - orient stays scale-local."""
        return [n for n in self.wiki.values() if n.scope == "global" and n.parent is None]

    def _engine_state(self) -> dict[str, Any]:
        """The engine's own standing agenda, read from the canon graph's health.

        Step 5 of the engine restructure: the frontier becomes the dreamer's
        backlog. Surfaces the learning to-do (``loose`` nodes, genuinely
        ``unsourced`` ones), the typed ``contradictions`` (the highest-signal
        find), the topology defects canon repair owns (orphans, dangling), and
        the inherited ``ancestor`` cohort to audit first on conflict. Built
        defensively and without fitness - a graph-build hiccup must never break
        the orient dashboard.
        """
        try:
            from laplace.pipeline.graph import CanonGraph

            g = CanonGraph.from_canon(self, with_fitness=False)
            h = g.health()
            # The repo root holds the occurrence artifacts (handoffs, soul/, diary)
            # the down-pointer resolves against: canon root is <repo>/src/laplace/canon.
            repo_root = self.root.parent.parent.parent
            bw = g.audit_both_ways(occurrence_root=repo_root)
        except Exception:  # noqa: BLE001 - the dashboard is a convenience, never a hard dep
            return {"available": False}

        def _cap(xs: list) -> list:
            return xs[:12]

        return {
            "available": True,
            "consistency_pass": h["pass"],
            "frontier": {
                "loose": _cap(h["frontier"]["loose"]),
                "unsourced": _cap(h["frontier"]["unsourced"]),
            },
            "contradictions": _cap(h["contradictions"]),
            "orphans": _cap(h["orphans"]),
            "dangling_count": len(h["dangling"]),
            "dead_wood_linked": _cap(h["dead_wood_linked"]),
            "ancestral_count": len(h["ancestral"]),
            # The both-ways frontier: how far the conceptric is from coarse-grainable
            # in both directions (provenance-down to the occurrence that earned each
            # node; draws-up to the idea it instantiates). The deep audit /goal eigen
            # works this down; surfaced here so it shrinks instead of staying unseen.
            "both_ways": {
                "earned": bw["earned_count"],
                "unearned": len(bw["unearned"]),
                "anchored": bw["anchored_count"],
                "unanchored": len(bw["unanchored"]),
                "closed": bw["both_ways_count"],
                "total": bw["node_count"],
                "stale_provenance": _cap(bw["stale_provenance"]),
            },
            "hint": (
                "Engine to-do: close the frontier and the topology defects "
                "(canon_weaver owns repair); a contradiction is the highest-signal "
                "find. The ancestral cohort is the pre-provenance baseline - "
                "closure is provenance, not completion, so audit it first when "
                "something conflicts rather than racing to empty it. The both-ways "
                "frontier (unearned/unanchored) is the deep both-ways audit's to-do: "
                "wire each node's provenance-down (earned_by the occurrence) and "
                "draws-up (the idea it instantiates), one grounded node at a time."
            ),
        }

    def dashboard(self) -> dict[str, Any]:
        """The landing view when no task is in focus: what is in play, by project
        and by activity, so a session with an unclear goal can pick a thread
        rather than guess. Live per-result status lives in each project's
        HANDOFF.md (not restated here); engine to-dos live in AUTONOMY_BACKLOG.md
        and, for the canon graph itself, in ``engine_state`` below.
        """
        # INVENTORY vs ROUTING (the demotion): the project roster + live convergence state now
        # derive from the pipeline registry (project_states) - the inventory authority on what
        # projects exist. index.yaml's domains: block is DEMOTED to routing authority only (which
        # wiki namespace a project rides), no longer the roster; domain here is a routing label.
        from laplace.pipeline import registry as _registry
        projects = []
        try:
            reg_projs = _registry.all_projects()
            states = _registry.project_states(self.root.parent.parent.parent)
        except Exception:  # noqa: BLE001 - the roster is a convenience, never a hard dep
            reg_projs, states = {}, []
        for st in states:
            projects.append({
                "domain": _dashboard_domain(reg_projs.get(st["name"])),
                "project": st["name"],
                "kind": st["kind"],
                "state": st["state"],
                "rounds": st["rounds_n"],
                "updated": st["updated"],
            })
        activities: dict[str, list[str]] = {"generating": [], "staging": [], "evaluating": []}
        for sk in self.skills.values():
            if sk.status == "deprecated":
                continue
            activities.setdefault(sk.activity if sk.activity in activities else "staging", []).append(sk.name)
        return {
            "hint": (
                "No clear task in focus. Pick a project to resume, choose an activity "
                "(generating | staging | evaluating), or restate the goal in a sentence. "
                "Each project's live status is in its HANDOFF.md; engine to-dos are in "
                "AUTONOMY_BACKLOG.md."
            ),
            "active_projects": projects,
            "activities": activities,
            "domains": list(self.domains().keys()),
            "engine_state": self._engine_state(),
        }

    # -- the orient bundle --------------------------------------------------
    def orient(self, goal: str, domain: str | None = None, grade: int = 0) -> dict[str, Any]:
        """Project a grade-local context map for a goal - the graded orient.

        The "understand the goal" third of the loop, reconstructed the way the
        self already is: ``grade=0`` (the default) returns a MAP - every relevant
        node as a HANDLE (title + an ``essence`` digest + a mechanical ``descend``
        call), never the full body. The body is fetched on demand (a subagent when
        a level would overwhelm) so orient stays bounded as the conceptric grows -
        inlining every matched body is what blew the context cap. ``grade>=1`` is a
        deliberate deep pull that inlines the matched bodies.
        """
        domain = domain or self.infer_domain(goal)
        matched = {n.ref for n in self.rank_wiki(goal, domain)}

        foundation = []
        for n in self.global_foundation():
            item = {"ref": f"canon://{n.ref}", "title": n.title, "tags": n.tags}
            if n.ref in matched:
                # The co-activation signal is grade-independent: a node fires
                # because it MATCHED the goal, not because its body was inlined.
                item["relevant"] = True
                body = self.resolve(n.ref)[1]
                if grade >= 1:
                    item["content"] = body                # deliberate deep pull
                else:
                    item["essence"] = _essence(body)      # grade-0 handle, not the body
                    item["descend"] = f"laplace_resolve('canon://{n.ref}')"
            kids = self.children(n.ref)
            if kids:
                # Coarse node: show that it stands in for a hidden subgraph and
                # how to open it, but do NOT inline the interior. The reader
                # descends deliberately - the voice corpus is the canonical case.
                item["nested_count"] = len(kids)
                item["nested"] = [{"ref": f"canon://{k.ref}", "title": k.title} for k in kids]
                item["descend"] = f"laplace_resolve('canon://{n.ref}') to open this cluster"
            foundation.append(item)

        domain_context = []
        if domain:
            for n in self.domain_nodes(domain):
                d_item = {"ref": f"canon://{n.ref}", "title": n.title}
                body = self.resolve(n.ref)[1]
                if grade >= 1:
                    d_item["content"] = body
                else:
                    # grade-local: the active domain's axioms are handles too, so a
                    # drafting goal does not inline every axiom body into the bundle.
                    d_item["essence"] = _essence(body)
                    d_item["descend"] = f"laplace_resolve('canon://{n.ref}')"
                domain_context.append(d_item)

        skills = {"generating": [], "staging": [], "evaluating": []}
        for sk in self.rank_skills(goal, domain):
            s = sk.summary()
            s["ref"] = f"canon://skills/{sk.name}"
            if sk.backing:
                s["run"] = f"laplace_run(skill={sk.name!r}, target=...)"
            
            activity = sk.activity if sk.activity in skills else "staging"
            skills[activity].append(s)

        bundle: dict[str, Any] = {
            "goal": goal,
            "domain": domain,
            "grade": grade,
            "loop": (
                "orient (you are here) -> select activity (generating|staging|evaluating) "
                "-> execute via laplace_skill / laplace_run"
            ),
            "foundation": foundation,
            "domain_context": domain_context,
            "skills": skills,
            # Top-level refs only: a coarse node stands in for its interior, which
            # lives in ``clusters`` and is resolved on descent. The full canon is
            # still addressable, just hierarchised rather than flattened here.
            "available_refs": sorted(
                [f"canon://{r}" for r, nn in self.wiki.items() if nn.parent is None]
                + [f"canon://skills/{n}" for n in self.skills]
            ),
            "clusters": self.clusters(),
        }

        # The orchestration disposition, stated by the bundle so it is enforced by
        # the orient, not left to memory (the same move as generation_discipline).
        # This bundle is a grade-0 MAP; you are the orchestrator that holds it and
        # fetches deeper grades as separate, bounded, returnable calls - a subagent
        # when a level would overwhelm - so no context ever holds the whole.
        bundle["orchestration"] = {
            "law": "you are the orchestrator; at grade 0 you hold the map, not the bodies",
            "dispatch_law": (
                "an agent prompt is reconstruct(node, goal), never read(file): compile "
                "every dispatch via laplace.pipeline.dispatch.compile_dispatch (the "
                "graded-node kernel + OBJECT at depth + POLICY handles) - hand-written "
                "briefs are the flatten reflex one level up"
            ),
            "do": (
                "this bundle is the grade-0 map - handles with an `essence` and a "
                "`descend` call, never the full body. Pull a body only when the task "
                "needs it, via its `descend`. When a descend would overwhelm your "
                "context (a large node, a whole cluster, the corpus), dispatch it to a "
                "SUBAGENT that descends, distils, and returns only what you asked - so "
                "no level holds the whole and each navigates its distillate back. "
                "Re-call orient with grade>=1 only for a deliberate deep pull."
            ),
            "fetch": {
                "canon node / domain axiom": "laplace_resolve(ref)  (or a subagent given the ref)",
                "directory object / file": "laplace_shard(action='name', query=<name>, grade=k)",
                "the engine-self": "laplace_reconstruct_self(grade=k)",
                "corpus record / soul fragment": (
                    "the `memory` block's refs (soul is refs-only, never inlined)"
                ),
            },
        }

        # orient-guard: when the task is underdetermined - no domain inferred, or
        # an empty/blank goal - surface a dashboard (active projects, activities,
        # domains) so the session can pick a thread rather than guess, plus the
        # candidate domains. Everything needed to re-orient, in one response.
        if domain is None or not goal.strip():
            bundle["dashboard"] = self.dashboard()
        if domain is None:
            candidate_domains = [
                {
                    "name": dname,
                    "tags": list((dmeta or {}).get("tags", [])),
                }
                for dname, dmeta in self.domains().items()
            ]
            bundle["domain_recovery"] = {
                "hint": (
                    "Domain could not be inferred from the goal. "
                    "Pass domain=<name> explicitly or rephrase the goal using "
                    "domain-specific language. Candidate domains are listed below."
                ),
                "candidate_domains": candidate_domains,
            }

        # The full-conceptric reach (META_TEST_2026-06-05): orient's foundation/
        # domain/skills are only the canon layer. Attach what the goal routes to
        # in the rest of memory — the corpus (the local particular), the soul (the
        # global taste), and the engine's own dated self-knowledge — so every
        # orient reaches what the engine actually remembers, up and down, and a
        # result can re-derive the assumptions it rests on instead of leaning on
        # context outside the engine (the exogenous door). Defensive: a missing
        # store yields an empty slice, never a broken orient.
        try:
            tokens = _tokenize(goal)
            repo_root = self.root.parent.parent.parent
            bundle["memory"] = {
                "corpus": _route_corpus(tokens, repo_root, 6),
                "soul": _route_soul(tokens, repo_root, 6),
                "self_knowledge": _route_self_knowledge(tokens, repo_root, 6),
                "project": _route_project_substrate(tokens, repo_root, 6),
                "note": (
                    "the conceptric the goal reaches beyond the canon layer "
                    "(the same retrieval as laplace route); the soul returns refs "
                    "to pull, never inlined content"
                ),
            }
        except Exception:  # noqa: BLE001 - memory reach is a convenience, never a hard dep
            bundle["memory"] = {"available": False}

        # Eigen-as-its-own-corpus: the hello reconstructs the engine-self as a graded
        # PROJECTION (the grade-0 fixed point - what's true now / do next / blocked on the
        # author) instead of a linear read of five whole files (EIGEN_PROTOCOL Part A, the
        # engine's own root disease: read everything, work from raw, every session). At
        # grade 0 the self is its OWN bounded call (the hello's first action), so orient
        # carries a POINTER, not the inlined projection - the orchestration law applied to
        # orient's own self-reach (don't inline what is one cheap descend away). The full
        # projection inlines at grade>=1. Defensive - never a hard dependency.
        try:
            from laplace.engine.self_corpus import reconstruct_self

            if grade >= 1:
                bundle["self_projection"] = reconstruct_self(
                    self.root.parent.parent.parent, grade=0
                )
            else:
                bundle["self_projection"] = {
                    "grade0_handle": True,
                    "fire": "laplace_reconstruct_self(grade=0)",
                    "note": (
                        "the engine-self fixed point - fetched as a separate bounded call, "
                        "not inlined into every orient (descend on demand)"
                    ),
                }
        except Exception:  # noqa: BLE001 - the self-projection is a convenience, never a hard dep
            pass

        # The blind-generation directive (META_TEST_2026-06-05, the meta-dream's
        # forge): when the goal is to generate an artefact, the orchestrator must
        # not be both builder and judge. State the discipline here, not only as a
        # surfaced skill, so the loop is *enforced* by the orient, not left to be
        # remembered: spawn a blind, context-starved generator whose context the
        # orchestrator architects from this bundle's `memory` block (the
        # conceptric the router reaches - the context, not the answer), and judge
        # its result from OUTSIDE its context. The skill carries the checklist.
        if _tokenize(goal) & self._GENERATING_INTENT_TOKENS:
            bundle["generation_discipline"] = {
                "law": "builder != judge - a context that builds an artefact cannot judge it",
                "do": (
                    "spawn a blind, context-starved generator; architect its context "
                    "explicitly from the `memory` block (the conceptric the router "
                    "reaches, not the answer); judge its result from outside its context; "
                    "route fixes back into the conceptric and re-project"
                ),
                "skill": "canon://skills/orchestrated_generation",
            }

        return bundle

    def route(self, goal: str, k: int = 6) -> dict[str, Any]:
        """One routing into the FULL conceptric — up and down, the one thing.

        The meta test (``META_TEST_2026-06-05_context-manifests.md``) found that
        ``orient`` reaches only the thin canon-wiki layer: the **corpus** (the
        local particular), the **soul** (the global taste), and the engine's own
        **self-knowledge** (architecture / protocol / open-stack / the dated
        trace) are all invisible to goal-routing. So the local reconstructor
        cannot function, and results lean on context the engine cannot itself
        reach — the open exogenous door (a result that cannot re-derive the
        assumption it claims to rest on).

        This is the router that lets the engine *remember*: a single goal-matched
        retrieval across every store it remembers from, using the same
        ``_tokenize`` ∩ blob scorer that already powers ``orient``. Up (the
        canon + the soul) and down (the corpus + the dated self-knowledge) are
        one routing, not two. ``orient`` is left untouched — its consumers keep
        their contract; ``route`` is the wider organ the reconstructor calls.

        Built defensively: a missing store yields an empty slice, never an error.
        The soul is matched but its **content is withheld** — the router returns
        the fragment to pull, and pulling stays a deliberate act (the sample is
        verbatim and private; it is never inlined by a retrieval call).
        """
        tokens = _tokenize(goal)
        repo_root = self.root.parent.parent.parent
        domain = self.infer_domain(goal)
        canon_hits = {
            "domain": domain,
            "wiki": [f"canon://{n.ref}" for n in self.rank_wiki(goal, domain)],
            "skills": [sk.name for sk in self.rank_skills(goal, domain)],
        }
        return {
            "goal": goal,
            "canon": canon_hits,
            "corpus": _route_corpus(tokens, repo_root, k),
            "soul": _route_soul(tokens, repo_root, k),
            "self_knowledge": _route_self_knowledge(tokens, repo_root, k),
            "project": _route_project_substrate(tokens, repo_root, k),
            "note": (
                "one routing into the full conceptric (canon + corpus + soul + "
                "self-knowledge + project substrate); up and down are one thing. "
                "These slices are the particular `orient` alone cannot reach."
            ),
        }


def _route_corpus(tokens: set[str], repo_root: Path, k: int) -> list[dict[str, Any]]:
    """Goal → corpus records (the down-stream local reconstructor's literature).

    Scores each ``corpus.bib`` record by token overlap on its topical fields
    (title/keywords/cluster/theme/claim/tldr — not the long summary, so the match
    stays sharp), and returns the top ``k`` with their cluster, trust status, and
    claim. This is the path the meta test found missing entirely: ``orient`` never
    read the corpus, so a goal retrieved zero records."""
    bib = repo_root / "corpus" / "corpus.bib"
    if not bib.exists():
        return []
    try:
        from laplace.pipeline.graph import _parse_bib
        text = bib.read_text(encoding="utf-8")
    except (OSError, ImportError):
        return []
    scored: list[tuple[int, str, dict[str, str]]] = []
    for key, f in _parse_bib(text):
        blob = " ".join(f.get(x, "") for x in ("title", "keywords", "cluster", "theme", "claim", "tldr"))
        s = len(tokens & _tokenize(blob))
        if s > 0:
            scored.append((s, key, f))
    scored.sort(key=lambda r: (-r[0], r[1]))
    return [
        {"key": key, "cluster": f.get("cluster", ""), "status": f.get("status", ""),
         "claim": f.get("claim", ""), "score": s}
        for s, key, f in scored[:k]
    ]


def _route_soul(tokens: set[str], repo_root: Path, k: int) -> list[dict[str, Any]]:
    """Goal → soul fragments (the global self's taste, made reachable).

    The judgement centre's ground truth. Scores each sealed entry by token
    overlap, returns the ref to pull — **never the content** (verbatim, private,
    pulled deliberately). Reaches both ``soul/`` (the transferred self) and
    ``soul_corpus/sealed/`` (the soul-dump distillate, F24): the carrier rides
    every loop as a REF, the content stays sealed. Before this, the soul sat
    outside the wiki dir and was invisible to every retrieval."""
    scored: list[tuple[int, str]] = []
    for base in ("soul", "soul_corpus/sealed"):
        d = repo_root / base
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                continue
            s = len(tokens & _tokenize(text))
            if s > 0:
                scored.append((s, f"{base}/{p.name}"))
    scored.sort(key=lambda r: (-r[0], r[1]))
    return [{"ref": ref, "score": s} for s, ref in scored[:k]]


def _route_self_knowledge(tokens: set[str], repo_root: Path, k: int) -> list[dict[str, Any]]:
    """Goal → the engine's own self-knowledge, at section granularity.

    The architecture, the protocol, the open stack, the live + dated handoffs, the diary, and the
    founding META_TEST docs — the frame a context-starved reconstructor misses when it uses
    ``orient`` alone. The self-substrate is the one definition (``self_shard.self_substrate``, N21):
    the SAME discovered set the hello reconstructs from, read through the SAME sealed reader
    (``read_source``). So orient and the hello no longer re-derive "what is the self" from two
    hardcoded lists that can drift — the double-reload collapses to one substrate, one reader.
    Indexed per ``## `` section so a goal surfaces the relevant section (file + heading), not a file."""
    try:
        from laplace.engine.self_shard import read_source, self_substrate

        subs = self_substrate(repo_root)
        ordered: list[str] = []
        seen: set[str] = set()
        for role in ("fixed_point", "map", "guides", "protocol", "handoffs", "meta"):
            for n in subs.get(role, []):
                if n not in seen:
                    seen.add(n)
                    ordered.append(n)

        def _read_node(name: str) -> str:
            return read_source(repo_root, name)
    except Exception:  # noqa: BLE001 - fall back to a direct walk if the shard module is unavailable
        base = ["EIGEN_ARCHITECTURE.md", "EIGEN_PROTOCOL.md", "EIGEN_DIARY.md",
                "OPEN_STACK.md", "HANDOFF.md"]
        ordered = [n for n in base if (repo_root / n).exists()]
        ordered += [p.name for p in sorted(repo_root.glob("SESSION_HANDOFF_*.md"))]
        ordered += [p.name for p in sorted(repo_root.glob("META_TEST_*.md"))]

        def _read_node(name: str) -> str:
            try:
                return (repo_root / name).read_text(encoding="utf-8")
            except OSError:
                return ""

    scored: list[tuple[int, str, str]] = []
    for name in ordered:
        text = _read_node(name)
        if not text:
            continue
        for sec_title, sec_body in _split_md_sections(text):
            s = len(tokens & _tokenize(sec_title + " " + sec_body))
            if s > 0:
                scored.append((s, name, sec_title))
    scored.sort(key=lambda r: (-r[0], r[1], r[2]))
    return [{"file": fn, "section": st, "score": s} for s, fn, st in scored[:k]]


def _route_project_substrate(tokens: set[str], repo_root: Path, k: int) -> list[dict[str, Any]]:
    """Goal → the project particular (the down-stream local reconstructor proper).

    The closure loop found the router reached the engine's *global* self-knowledge and
    the corpus, but not the **project substrate** — the conceptric inputs, distillations,
    and per-project handoffs where a result's *particular* lives (e.g. the operational
    definition of the order parameter φ). This store reaches it: the per-project
    ``inputs/*.md`` (substrates / blueprints / distillations) and each project's own
    ``HANDOFF.md`` / ``OPEN_STACK.md``, indexed per section. This is what 'reconstructs
    what you should already know' for a task — the stored particular conceptric."""
    files = sorted(repo_root.glob("*/inputs/*.md"))
    files += sorted(repo_root.glob("*/HANDOFF.md"))
    files += sorted(repo_root.glob("*/OPEN_STACK.md"))
    scored: list[tuple[int, str, str]] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = p.relative_to(repo_root).as_posix()
        for sec_title, sec_body in _split_md_sections(text):
            s = len(tokens & _tokenize(sec_title + " " + sec_body))
            if s > 0:
                scored.append((s, rel, sec_title))
    scored.sort(key=lambda r: (-r[0], r[1], r[2]))
    return [{"file": fn, "section": st, "score": s} for s, fn, st in scored[:k]]


def _split_md_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) on ``## ``/``# `` headers. The whole
    head (before the first header) is returned under an empty heading so a
    title-only file still contributes."""
    sections: list[tuple[str, str]] = []
    cur_title, cur_lines = "", []
    for line in text.splitlines():
        if line.startswith("# ") or line.startswith("## "):
            if cur_lines or cur_title:
                sections.append((cur_title, "\n".join(cur_lines)))
            cur_title, cur_lines = line.lstrip("# ").strip(), []
        else:
            cur_lines.append(line)
    if cur_lines or cur_title:
        sections.append((cur_title, "\n".join(cur_lines)))
    return sections


def _read_head(path: Path, limit: int = 8192) -> str:
    """Read only the head of a markdown file - enough for its YAML frontmatter
    (always at the very top) and first ``# `` heading. Wiki/skill discovery never
    needs the full body, so capping the read keeps load cost scaling with file
    COUNT, not total canon size - orient stays cheap as the canon grows."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def _first_heading(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _derive_parent(ref: str, refs: set[str]) -> str | None:
    """A node's coarse parent, derived from its ref path: the ``index`` of its
    directory stands in for everything beneath it.

    ``voice_corpus/registers`` -> ``voice_corpus/index``. A directory's own
    ``index`` climbs one level (``a/b/index`` -> ``a/index``), so clusters nest
    to any depth. A ref whose directory has no ``index`` is top-level. Explicit
    ``parent`` in the manifest overrides this. The mechanism is the
    hierarchicalisation the engine is built on - a coarse node stands in for its
    subgraph, so orient never flattens the whole tree onto the top level.
    """
    parts = ref.split("/")
    dirs = parts[:-2] if parts[-1] == "index" else parts[:-1]
    if not dirs:
        return None
    candidate = "/".join(dirs) + "/index"
    return candidate if candidate in refs and candidate != ref else None


def _canon_fingerprint(root: Path) -> tuple[tuple[str, int], ...]:
    """A cheap signature of the canon's on-disk state: the mtime of every file
    that feeds a load (the manifest, the lifecycle overlay, and every skill and
    wiki source).

    Any forge, lifecycle write, or hand edit changes the signature, so the live
    tools pick up on-disk canon changes within the running server process - no
    restart required. The cost is a few dozen ``stat`` calls per load.
    """
    sources = [root / "index.yaml", root / "lifecycle.yaml"]
    sources += sorted((root / "skills").glob("*/SKILL.md"))
    sources += sorted((root / "wiki").rglob("*.md"))
    sig: list[tuple[str, int]] = []
    for p in sources:
        try:
            sig.append((str(p), p.stat().st_mtime_ns))
        except OSError:
            continue
    return tuple(sig)


def _ensure_seeded(root: Path) -> None:
    """First-use bootstrap: if ``LAPLACE_CANON`` points at a location with no
    canon yet (no ``index.yaml``), seed it from the packaged canon.

    Lets a fresh machine - or a new agent (Codex, Gemini) - point at a shared
    canon path that the engine populates on first load, rather than failing
    empty. A real canon (``index.yaml`` present) is never overwritten. The copy
    runs under the canon write lock so two agents starting at once against an
    empty shared path cannot interleave a half-seed.
    """
    if root == _PACKAGED_CANON:
        return
    if (root / "index.yaml").exists():
        return
    if not (_PACKAGED_CANON / "index.yaml").exists():
        return
    # Lazy import: avoids a module-load cycle (locking -> telemetry only).
    from laplace.pipeline.locking import CanonBusy, canon_lock

    try:
        with canon_lock(timeout=60):
            if (root / "index.yaml").exists():  # re-check under the lock
                return
            root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(_PACKAGED_CANON, root, dirs_exist_ok=True)
    except CanonBusy:
        # Another agent is seeding the same path; its copy will land. Proceed to
        # load - by read time the seed is in place (or the next fresh load gets it).
        return


# root_str -> (fingerprint, canon). The canon is reused until its fingerprint
# changes, so edits on disk are reflected without a fresh session.
_CANON_CACHE: dict[str, tuple[tuple[tuple[str, int], ...], Canon]] = {}


def get_canon(fresh: bool = False) -> Canon:
    """Return the active canon, reloading automatically when the canon files on
    disk change. ``fresh=True`` forces an immediate reload regardless.
    """
    root = canon_root()
    _ensure_seeded(root)
    root_str = str(root)
    fingerprint = _canon_fingerprint(root)
    cached = _CANON_CACHE.get(root_str)
    if not fresh and cached is not None and cached[0] == fingerprint:
        return cached[1]
    canon = Canon.load(root)
    _CANON_CACHE[root_str] = (fingerprint, canon)
    return canon
