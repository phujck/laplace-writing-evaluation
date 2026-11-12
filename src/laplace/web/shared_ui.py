"""The SHARED UI layer - the hymn sheet the six applets sing from.

Serves shared assets through the explicit basename allowlist and fenced asset
subtrees, plus ``/shared/plan?corpus=`` - the corpus' projection plan
(``synthetics papers/<corpus>/manuscript/projection_plan.json``) with a
node -> section index computed for the cross-links ("show in projection").

Pure handler module, same contract as ``projection_viewer``: the scanner owns
the HTTP server and dispatches ``GET /shared/*`` here via :func:`handle`.
Never starts a server, never embeds (views never embed), never writes.

Traversal safety: only the explicit allowlist and fenced subtrees resolve to
assets; traversal shapes are refused. Writing captures these bytes and validates
the reachable literal import closure of its captured entrypoints before serving
the bundle. The plan path is resolved through the project registry (an unknown
corpus name never touches the filesystem) with a resolved-containment check on top.
"""

from __future__ import annotations
from laplace.manuscript.manuscript_versions import _SEGMENT_RE, versions_payload
from laplace.manuscript.manuscript_plan import plan_payload

import json
import re
import time as _time
from laplace.core.observe import iso_utc as _iso, mtime as _mtime, relative as _rel
from laplace.pipeline import registry
from laplace.pipeline.registry import MINTED_PDF_RE as _MINTED_PDF_RE
import hashlib
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import urljoin, urlsplit

_STATIC = Path(__file__).resolve().parent / "static_shared"

# the allowlist IS the traversal fence: only these exact names resolve to files
_ASSETS = {
    # the design tokens (M5 C3): linked by the shell page before workspace.css and by
    # walk.html before its inline style
    "tokens.css": "text/css; charset=utf-8",
    "workspace-inspector.mjs": "text/javascript; charset=utf-8",
    "feedback-route.mjs": "text/javascript; charset=utf-8",
    "feedback-review-context.mjs": "text/javascript; charset=utf-8",
    "feedback-route-port.mjs": "text/javascript; charset=utf-8",
    "feedback-route.css": "text/css; charset=utf-8",
    "review-setup.mjs": "text/javascript; charset=utf-8",
    "review-setup-port.mjs": "text/javascript; charset=utf-8",
    "review-setup.css": "text/css; charset=utf-8",
    "local-document-intake.mjs": "text/javascript; charset=utf-8",
    "local-document-intake-port.mjs": "text/javascript; charset=utf-8",
    "local-document-intake.css": "text/css; charset=utf-8",
    "provider-options.mjs": "text/javascript; charset=utf-8",
    "workspace-interaction.mjs": "text/javascript; charset=utf-8",
    "workflow-action-context.mjs": "text/javascript; charset=utf-8",
    "workspace-workflow-action.mjs": "text/javascript; charset=utf-8",
    # shared human presentation (chips, object headers, lazy exact reads, hunk cards,
    # ordered plan, coordination ladder) and the state-observed interactive guide
    "workspace-presentation.mjs": "text/javascript; charset=utf-8",
    "workspace-presentation.css": "text/css; charset=utf-8",
    "pending-read.mjs": "text/javascript; charset=utf-8",   # V9: a pending owner read says for how long it has waited
    "workspace-guide.mjs": "text/javascript; charset=utf-8",
    "prepared-work.mjs": "text/javascript; charset=utf-8",
    "derived-output.mjs": "text/javascript; charset=utf-8",
    "publication-editions.mjs": "text/javascript; charset=utf-8",
    "manuscript-editor.mjs": "text/javascript; charset=utf-8",
    "source-effect.mjs": "text/javascript; charset=utf-8",
    "proposal-resolution.mjs": "text/javascript; charset=utf-8",
    "proposal-resolution.css": "text/css; charset=utf-8",
    "workspace-spine.mjs": "text/javascript; charset=utf-8",
    "reader-state.mjs": "text/javascript; charset=utf-8",
    "reader-restructure.mjs": "text/javascript; charset=utf-8",
    "reader-logical-restructure.mjs": "text/javascript; charset=utf-8",
    "profile-preferences.mjs": "text/javascript; charset=utf-8",
    "session-preferences.mjs": "text/javascript; charset=utf-8",
    "workspace-backlog.mjs": "text/javascript; charset=utf-8",
    "workspace-source-inspector.mjs": "text/javascript; charset=utf-8",
    "plan-publication.mjs": "text/javascript; charset=utf-8",
    "workspace-spine.css": "text/css; charset=utf-8",
    "manuscript-document-view.mjs": "text/javascript; charset=utf-8",
    "document-template.mjs": "text/javascript; charset=utf-8",
    "manuscript-source-client.mjs": "text/javascript; charset=utf-8",
    "exact-source-editor.mjs": "text/javascript; charset=utf-8",
    "manuscript-editor.css": "text/css; charset=utf-8",
    "workspace-material-observation.mjs": "text/javascript; charset=utf-8",
    "writing-artifact.mjs": "text/javascript; charset=utf-8",
    "writing-owner-read.mjs": "text/javascript; charset=utf-8",
    "writing-artifact.css": "text/css; charset=utf-8",
    "workspace-analysis.mjs": "text/javascript; charset=utf-8",
    "workspace-analytics.mjs": "text/javascript; charset=utf-8",
    "workspace-sessions.mjs": "text/javascript; charset=utf-8",  # the Sessions page (app=activity), wave 9
    "workspace-development.mjs": "text/javascript; charset=utf-8",  # the open session's Development section, wave 13
    "workspace-history.mjs": "text/javascript; charset=utf-8",
    "workspace-writing-style.mjs": "text/javascript; charset=utf-8",
    "workspace-project.mjs": "text/javascript; charset=utf-8",
    "workspace-app.mjs": "text/javascript; charset=utf-8",
    "workspace-owners.mjs": "text/javascript; charset=utf-8",   # the System owners app view (work.owner-discovery)
    "workflow-port.mjs": "text/javascript; charset=utf-8",  # guarded pipeline.workflow consumer
    "workflow-setting-choices.mjs": "text/javascript; charset=utf-8",
    "workspace-workflow-editor.mjs": "text/javascript; charset=utf-8",
    "workspace-workflow-history.mjs": "text/javascript; charset=utf-8",
    "workspace-workflow-operation.mjs": "text/javascript; charset=utf-8",
    "workspace-workflow-river.mjs": "text/javascript; charset=utf-8",
    "turn-events.mjs": "text/javascript; charset=utf-8",
    "workspace-workflow-editor.css": "text/css; charset=utf-8",
    "work-port.mjs": "text/javascript; charset=utf-8",   # the renderer-neutral selected Work port (P1)
    "work-port-outline.mjs": "text/javascript; charset=utf-8",   # its plain-DOM outline renderer (P1)
    "writing-request.mjs": "text/javascript; charset=utf-8",   # thin preserved writing response/request adapter
    "owner-request.mjs": "text/javascript; charset=utf-8",   # the neutral same-origin owner request carrier (P2)
    "selected-lifetime.mjs": "text/javascript; charset=utf-8",   # shared selection/generation/delivery/disposal (P2)
    "frontend-basis.mjs": "text/javascript; charset=utf-8",   # page-issued frontend basis and explicit refresh (P2)
    "history-telemetry.mjs": "text/javascript; charset=utf-8",
    "workspace-history.css": "text/css; charset=utf-8",
    "workspace-review.mjs": "text/javascript; charset=utf-8",
    "workspace-output.mjs": "text/javascript; charset=utf-8",
    "workspace-workflows.css": "text/css; charset=utf-8",
    "hymn.css": "text/css; charset=utf-8",
    "shell.js": "text/javascript; charset=utf-8",
    "inspector.js": "text/javascript; charset=utf-8",
    # the ONE client model (W0.3): {project, selection, decision}, URL-canonical,
    # the single fetch gateway. ESM, no deps; NOTHING consumes it yet (surfaces
    # arrive W1+), but it is served now so the smoke page + store_model harness load it.
    "store.mjs": "text/javascript; charset=utf-8",
    # Aisthesis Continuity's deterministic renderer.  It consumes only the exact
    # laplace.aisthesis-continuity-loom/1 geometry supplied by the read model and emits
    # native controls; no fetch, topology choice, acknowledgement or authority path.
    "continuity_loom.mjs": "text/javascript; charset=utf-8",
    # Aisthesis' next-generation /front carrier.  The carrier owns composition,
    # focus and contextual-room mounting only; all truth remains in the server's
    # immutable front model and the existing typed organ projections.
    "front_carrier.mjs": "text/javascript; charset=utf-8",
    # Root-level semantic-object comment overlay. It delegates only through stable
    # producer-owned anchors and the canonical /front/feedback seam; no browser store.
    "front_feedback.mjs": "text/javascript; charset=utf-8",
    # Work's manuscript-specific renderer.  It consumes only the immutable
    # laplace.aisthesis-manuscript-workbench/1 projection and returns every focus,
    # posture and grade transition to the carrier's existing shared URL store.
    "manuscript_work_surface.mjs": "text/javascript; charset=utf-8",
    # THE ARTEFACT SURFACE's pane logic (W2): reader/annotate/edit, the version rail, the
    # diff — lifted out of artefact.html to hold its ≤8KB inline-script budget. A shared
    # module joined to store.mjs (imports it), not a rostered surface (budgets don't apply).
    "artefact-panes.mjs": "text/javascript; charset=utf-8",
    # THE CONCEPTRIC SURFACE's pane logic (W3): the graded descent (stock), the ascend/descend
    # cards (local), spine, gaps (audit), the node card with the evidence lane + "argues in"
    # doors — lifted out of conceptric.html to hold its ≤8KB inline-script budget. Joined to
    # store.mjs (imports it), the one fetch path; not a rostered surface (budgets don't apply).
    "conceptric-panes.mjs": "text/javascript; charset=utf-8",
    # the STORYBOARD surface's pane logic (W4): the board as the acting centre —
    # section cards that expand in place, the rank strip, the residue tray (planned/
    # realised, retire arm-to-fire), the coverage inverse, the run panel, the
    # restructure door. Lifted out of storyboard.html to hold its ≤8KB inline-script
    # budget. Joined to store.mjs (the one fetch path); not a rostered surface.
    "storyboard-panes.mjs": "text/javascript; charset=utf-8",
    # THE DESK COCKPIT's pane logic (W5): the strata filter row + the decision cards, each
    # expanding in place into the four-zone cockpit (context/consequences/tools/deep-links).
    # A SHARED module — /artefact's findings tray reuses its renderCockpit + armToFire, so the
    # cockpit idiom lives once. Joined to store.mjs (the one fetch path); not a rostered surface.
    "desk-panes.mjs": "text/javascript; charset=utf-8",
    # THE ASSET SURFACE's pane logic (W7): the asset CARD + its COCKPIT (context = the
    # rendered figure / the derivation steps; consequences = what a regen rebuilds; tools =
    # assess verbs + the banked-edit door + manifest-only regen; deep-links = its landings +
    # nodes). THE ONE asset-cockpit implementation — the reader-side anchor layer
    # (artefact-panes.mjs) imports renderAssetCockpit so the SAME cockpit opens in place.
    # Joined to store.mjs + desk-panes.mjs's armToFire; not a rostered surface (budgets don't apply).
    "assets-panes.mjs": "text/javascript; charset=utf-8",
    # THE PIPELINE SURFACE's pane logic (W6): the chain as a BOARD from the release state
    # machine — organ CARDS with their dials in place (edit/undo ride /dials/op·/dials/undo,
    # the ONE write path), scoped arm/fire with a dry-run preview, the regrade-health read.
    # Joined to store.mjs (the one fetch path); not a rostered surface (budgets don't apply).
    "pipeline-panes.mjs": "text/javascript; charset=utf-8",
    # THE FOCUSSTATE RUNTIME (E3): the reusable focus/geometry engine — brief base altitude,
    # the hover lens (reveal, no reflow), pin/reallocate + exact restore, the highlight bus,
    # the return door. Exported as clean primitives the cockpit (and the editor next) join;
    # not a rostered surface (budgets do not apply).
    "engine.mjs": "text/javascript; charset=utf-8",
    # THE GROWTH COCKPIT's pane logic (E3): the brief for the selected corpus, counts that
    # materialise queues/coverage/ladder on open, the tension card's four-verb decision with
    # the REGOAL confirm gate. Joined to store.mjs + engine.mjs; not a rostered surface.
    "cockpit-panes.mjs": "text/javascript; charset=utf-8",
    # THE DASHBOARD's pane logic (W-DASH): the composed brief of the whole (delta-and-ask),
    # the count chips, and the project cards as the inventory materialised behind one open —
    # each card keeping its truth chips. Lifted out of dashboard.html so the entry stays a
    # thin brief shell under its 16KB first-paint law. Joined to store.mjs + engine.mjs.
    "dashboard-panes.mjs": "text/javascript; charset=utf-8",
    # THE LINEAGE SURFACE's pane logic (W-lineage, 2026-07-22): renders the brief base
    # altitude (GET /lineage/brief) and materializes the three views on focus — node-outward,
    # object-backward, the whole graph — over engine.mjs (the focus runtime) with a named
    # return door to the brief. Joined to store.mjs (the one fetch path) + engine.mjs; not a
    # rostered surface (budgets don't apply).
    "lineage-panes.mjs": "text/javascript; charset=utf-8",
    # THE STRUCTURAL GUIDE's pane logic (W-guide, 2026-07-22): renders /guide/data — the
    # engine account, the per-surface census FROM contract/surfaces/*.yaml, the session
    # story, the open promises both directions. Joined to store.mjs (the one fetch path).
    "guide-panes.mjs": "text/javascript; charset=utf-8",
    # THE SHARED RUN PANEL (W6): the run's live state + open work orders + scoped launch
    # doors (dry-run then arm-to-fire; model-heavy BANKS a work-order). Lifted so ONE
    # implementation serves BOTH the storyboard run pane AND the pipeline converge organ
    # (conception §7). Joined to store.mjs + desk-panes.mjs's armToFire; not a rostered surface.
    "run-tray.mjs": "text/javascript; charset=utf-8",
    # THE REDLINE WALK's whole front end (DESIGN_2026-08-10, the clean-room ruling): the
    # reader, the spine, the posture geometry. It imports store.mjs, the shared writing
    # modules named in walk.mjs's header (source-effect, manuscript-source-client,
    # reader-restructure, writing-owner-read, manuscript-editing, proposal-resolution) and
    # the vendored pdf.js/KaTeX — never engine.mjs, shell.js or *-panes.mjs. The allowlist
    # IS the serving fence, so the walk's module is named here like every other surface module.
    "walk.mjs": "text/javascript; charset=utf-8",
    # the walk's owner modules (M5 S2): walk.mjs is their composition root and imports each statically
    "walk-band.mjs": "text/javascript; charset=utf-8",
    "walk-bank.mjs": "text/javascript; charset=utf-8",
    "walk-base.mjs": "text/javascript; charset=utf-8",
    "walk-blocks.mjs": "text/javascript; charset=utf-8",
    "walk-card.mjs": "text/javascript; charset=utf-8",
    "walk-composer.mjs": "text/javascript; charset=utf-8",
    "walk-controls.mjs": "text/javascript; charset=utf-8",
    "walk-document.mjs": "text/javascript; charset=utf-8",
    "walk-drafts.mjs": "text/javascript; charset=utf-8",
    "walk-edit-history.mjs": "text/javascript; charset=utf-8",
    "walk-edit-input.mjs": "text/javascript; charset=utf-8",
    "walk-editing.mjs": "text/javascript; charset=utf-8",
    "walk-flip.mjs": "text/javascript; charset=utf-8",
    "walk-geometry.mjs": "text/javascript; charset=utf-8",
    "walk-media.mjs": "text/javascript; charset=utf-8",
    "walk-paragraph-ops.mjs": "text/javascript; charset=utf-8",
    "walk-pieces.mjs": "text/javascript; charset=utf-8",
    "walk-position.mjs": "text/javascript; charset=utf-8",
    "walk-review.mjs": "text/javascript; charset=utf-8",
    "walk-selection.mjs": "text/javascript; charset=utf-8",
    "walk-source-client.mjs": "text/javascript; charset=utf-8",
    "walk-where.mjs": "text/javascript; charset=utf-8",
    "manuscript-editing.mjs": "text/javascript; charset=utf-8",
    "writing-panel.mjs": "text/javascript; charset=utf-8",
    "writing-evidence.mjs": "text/javascript; charset=utf-8",
    "research-card.mjs": "text/javascript; charset=utf-8",
    "research-card.css": "text/css; charset=utf-8",
    "concept-explorer.mjs": "text/javascript; charset=utf-8",
    "concept-reader.mjs": "text/javascript; charset=utf-8",
    "engineering-support.mjs": "text/javascript; charset=utf-8",
    "writing-panel.css": "text/css; charset=utf-8",
    "project-work.mjs": "text/javascript; charset=utf-8",
    "project-work.css": "text/css; charset=utf-8",
    "writing-pdf.mjs": "text/javascript; charset=utf-8",
    "writing-pdf.css": "text/css; charset=utf-8",
    "workspace.mjs": "text/javascript; charset=utf-8",
    # the shell's domain controllers and shared element helpers (M5 S2 F1/F2): imported by workspace.mjs
    "workspace-chrome.mjs": "text/javascript; charset=utf-8",
    "workspace-conversation.mjs": "text/javascript; charset=utf-8",
    "workspace-walk-handlers.mjs": "text/javascript; charset=utf-8",
    "workspace-returns.mjs": "text/javascript; charset=utf-8",
    "workspace-context.mjs": "text/javascript; charset=utf-8",
    "workspace-help-door.mjs": "text/javascript; charset=utf-8",
    "workspace-notices.mjs": "text/javascript; charset=utf-8",
    "workspace-inspection.mjs": "text/javascript; charset=utf-8",
    "workspace-home.mjs": "text/javascript; charset=utf-8",
    "workspace-work-view.mjs": "text/javascript; charset=utf-8",
    "workspace-activity.mjs": "text/javascript; charset=utf-8",
    "workspace-proposals.mjs": "text/javascript; charset=utf-8",
    "workspace-figures.mjs": "text/javascript; charset=utf-8",
    "workspace-manuscript.mjs": "text/javascript; charset=utf-8",
    "workspace-reader-plan-view.mjs": "text/javascript; charset=utf-8",
    "workspace-argument.mjs": "text/javascript; charset=utf-8",
    "workspace-manuscript-outline.mjs": "text/javascript; charset=utf-8",
    "workspace-dom.mjs": "text/javascript; charset=utf-8",
    "workspace-research.mjs": "text/javascript; charset=utf-8",
    "research-workbench.mjs": "text/javascript; charset=utf-8",
    "workflow-impact-preview.mjs": "text/javascript; charset=utf-8",
    "research-geometry.mjs": "text/javascript; charset=utf-8",
    "research-navigation.mjs": "text/javascript; charset=utf-8",
    "research-workbench-state.mjs": "text/javascript; charset=utf-8",
    "research-workbench-view.mjs": "text/javascript; charset=utf-8",
    "research-workbench-conversation.mjs": "text/javascript; charset=utf-8",
    "research-object-context.mjs": "text/javascript; charset=utf-8",
    "research-workbench-readers.mjs": "text/javascript; charset=utf-8",
    "research-workbench-handover.mjs": "text/javascript; charset=utf-8",
    "research-workbench-outcome.mjs": "text/javascript; charset=utf-8",
    "research-workbench-actions.mjs": "text/javascript; charset=utf-8",
    "research-workbench-run.mjs": "text/javascript; charset=utf-8",
    "research-workbench.css": "text/css; charset=utf-8",

    # the shell side of the walk bridge (M5 readability P2): the message fence, ledger and route
    # table imported by workspace.mjs; the handlers stay in the shell
    "workspace-bridge.mjs": "text/javascript; charset=utf-8",
    "workspace-diagnostics.mjs": "text/javascript; charset=utf-8",
    "workspace-work.mjs": "text/javascript; charset=utf-8",
    # the Work controller's extracted sections (WORK-source-state-work-review-context-20261015): imported by
    # workspace-work.mjs; a served import must be captured here or the snapshot refuses at startup
    "workspace-work-review.mjs": "text/javascript; charset=utf-8",
    "workspace-review-evidence.mjs": "text/javascript; charset=utf-8",
    "workspace-task-trail.mjs": "text/javascript; charset=utf-8",
    "workspace-work-relations.mjs": "text/javascript; charset=utf-8",
    "workspace-work-navigator.mjs": "text/javascript; charset=utf-8",
    "workspace-work-observer.mjs": "text/javascript; charset=utf-8",
    # the typed topology view (M5 C4): imported by workspace-work.mjs and workspace-spine.mjs;
    # a served import must be captured here or the snapshot refuses at startup
    "workspace-topology.mjs": "text/javascript; charset=utf-8",
    # the help layer and the learning progress store (M5 C10): imported lazily by workspace.mjs
    "workspace-help.mjs": "text/javascript; charset=utf-8",
    "workspace-journeys.mjs": "text/javascript; charset=utf-8",
    "workspace-material.mjs": "text/javascript; charset=utf-8",
    "workspace-literature.mjs": "text/javascript; charset=utf-8",
    "literature-metadata.mjs": "text/javascript; charset=utf-8",
    "retained-source-literature.mjs": "text/javascript; charset=utf-8",
    "workspace-literature.css": "text/css; charset=utf-8",
    "sealed-reader-port.mjs": "text/javascript; charset=utf-8",
    "sealed-reader.mjs": "text/javascript; charset=utf-8",
    "workspace-session.mjs": "text/javascript; charset=utf-8",
    "conversation-reading.mjs": "text/javascript; charset=utf-8",
    "workspace.css": "text/css; charset=utf-8",
    # vendored pdf.js (self-contained, no CDN; see static_shared/pdfjs/VENDORED.md)
    "pdfjs/pdf.min.mjs": "text/javascript; charset=utf-8",
    "pdfjs/pdf.worker.min.mjs": "text/javascript; charset=utf-8",
    # vendored KaTeX (see static_shared/katex/VENDORED.md); fonts served by the
    # fenced-subtree rule below (20 woff2 files - a subtree, not 20 list entries)
    "katex/katex.min.js": "text/javascript; charset=utf-8",
    "katex/katex.min.css": "text/css; charset=utf-8",
    "katex/auto-render.min.js": "text/javascript; charset=utf-8",
    # vendored CodeMirror 6 — a single offline ESM bundle (W4.1; see
    # static_shared/vendor/codemirror/VENDORED.md). NOTHING loads it yet; W4.2
    # imports it via `import("/shared/vendor/codemirror/codemirror.bundle.mjs")`,
    # the same dynamic-ESM idiom the projection viewer uses for pdf.js.
    "vendor/codemirror/codemirror.bundle.mjs": "text/javascript; charset=utf-8",
    # wave 9: the frame every page shares (top bar, project switcher, narrow menu) and the Now page the app opens on
    "workspace-frame.mjs": "text/javascript; charset=utf-8",
    "workspace-now.mjs": "text/javascript; charset=utf-8",
}

# fenced subtrees: <prefix> -> allowed extensions. A name must be a plain
# segment path (no '..', no absolute), sit under the prefix, carry an allowed
# extension, and STILL resolve inside static_shared - checked, not assumed.
_SUBTREES = {
    "katex/fonts/": {".woff2": "font/woff2"},
    # the identity's vendored faces (Lora / Outfit / JetBrains Mono) — offline like katex,
    # never a CDN link (DESIGN_LANGUAGE.md §1).
    "fonts/": {".woff2": "font/woff2"},
}


@dataclass(frozen=True)
class AssetSnapshot:
    """One writing process's frontend bytes; project data is not part of it."""
    assets: Any
    pages: Any
    digest: str

    @property
    def identity(self) -> dict:
        return {"sha256": self.digest, "assets": len(self.assets),
                "templates": len(self.pages),
                "bytes": sum(len(value[1]) for value in self.assets.values())
                         + sum(len(value) for value in self.pages.values())}


_MODULE_IMPORTS = re.compile(r"""\bfrom\s*["']([^"']+)["']|\bimport\s*["']([^"']+)["']|\bimport\s*\(\s*["']([^"']+)["']\s*\)""")
_TEMPLATE_ASSETS = re.compile(r"""(?:src|href)\s*=\s*["'](/shared/[^"']+)["']""")


def _literal_module_references(source):
    return [next(value for value in match.groups() if value is not None)
            for match in _MODULE_IMPORTS.finditer(source)]


def validate_asset_snapshot(snapshot: AssetSnapshot, *, entrypoints=None) -> dict:
    """Check reachable literal module imports against the already captured bytes.

    This reuses the served-import traversal: static quoted imports and literal
    import(...) in local JavaScript, plus explicit captured-template resources.
    It does not execute/validate arbitrary JS or inspect data/network/disk. A
    missing imported file is an error even if it exists outside the allowlist.
    """
    pending=[]
    def target(importer, reference):
        if not reference.startswith(('/shared/','./','../')):return None
        path=urlsplit(urljoin(importer,reference)).path
        if not path.startswith('/shared/'):
            raise ValueError('Frontend dependency leaves /shared/: '+importer+' -> '+reference)
        name=path.removeprefix('/shared/')
        if name not in snapshot.assets:
            raise ValueError('Frontend dependency is absent from captured assets: '+importer+' -> '+reference+' ('+path+')')
        return name
    if entrypoints is None:
        for page, raw in snapshot.pages.items():
            text=raw.decode('utf-8');importer='template:'+page
            for reference in _TEMPLATE_ASSETS.findall(text):
                name=target('/'+page,reference)
                if name is not None:pending.append((name,importer))
            for reference in _literal_module_references(text):
                name=target('/'+page,reference)
                if name is not None:pending.append((name,importer))
    else:
        for name in entrypoints:
            reference=name if name.startswith('/shared/') else '/shared/'+name
            pending.append((target('/shared/',reference),'declared entry'))
    roots=sorted({name for name,_ in pending});seen=set();edges=0
    while pending:
        name, importer=pending.pop()
        if name in seen:continue
        seen.add(name);ctype,raw=snapshot.assets[name]
        if 'javascript' not in ctype:continue
        for reference in _literal_module_references(raw.decode('utf-8')):
            child=target('/shared/'+name,reference)
            if child is not None:
                edges+=1;pending.append((child,name))
    return {'entrypoints':roots,'reachable':sorted(seen),'local_import_edges':edges}


def capture_asset_snapshot(*, templates: dict[str, Path] | None = None) -> AssetSnapshot:
    """Capture the existing allowlist once, before a writing server accepts reads.

    Reachable missing dependencies refuse before the snapshot is published.
    An absent dormant asset stays absent for that process. New files/allowlist entries
    become visible only together in a freshly started writing process. Scanner
    callers that do not supply a snapshot retain their existing live behavior.
    """
    assets = {}
    for name, ctype in _ASSETS.items():
        path = (_STATIC / name).resolve()
        if path.is_relative_to(_STATIC.resolve()) and path.is_file():
            assets[name] = (ctype, path.read_bytes())
    for prefix in _SUBTREES:
        directory = _STATIC / prefix
        for path in directory.iterdir() if directory.is_dir() else []:
            name = prefix + path.name
            resolved = _subtree_asset(name)
            if resolved and resolved[0].is_file():
                assets[name] = (resolved[1], resolved[0].read_bytes())
    if templates is None:
        templates = {"project": Path(__file__).with_name("pipeline.html"),
                     "walk": Path(__file__).with_name("walk.html")}
    pages = {name: path.read_bytes() for name, path in templates.items()}
    digest = hashlib.sha256()
    for name, (_, value) in sorted(assets.items()):
        digest.update(name.encode()); digest.update(b"\0"); digest.update(value); digest.update(b"\0")
    for name, value in sorted(pages.items()):
        digest.update(name.encode()); digest.update(b"\0"); digest.update(value); digest.update(b"\0")
    snapshot=AssetSnapshot(MappingProxyType(assets), MappingProxyType(pages), digest.hexdigest())
    validate_asset_snapshot(snapshot)
    return snapshot


FRONTEND_BASIS_META = "laplace-frontend-basis"


def issued_page(snapshot: AssetSnapshot, name: str) -> bytes | None:
    """The captured page template as issued to one opened view, carrying the snapshot it was served from.

    The basis is the frozen snapshot's own digest (templates and assets captured once before reads), written into
    the served bytes as ``<meta name="laplace-frontend-basis" content="<sha256>">`` before ``</head>``; the captured
    template itself is unchanged, so the basis never hashes itself. It names the frontend this view was opened
    from (an issued/open-view basis), not an attestation of every module the page later imports. A template
    without ``</head>`` is served unchanged and the view's basis stays unknown. ``/authoring/health`` reports the
    currently served basis as ``frontend_bundle.sha256``; the page compares the two (frontend-basis.mjs).
    """
    page = snapshot.pages.get(name)
    if page is None or b"</head>" not in page:
        return page
    meta = b'<meta name="' + FRONTEND_BASIS_META.encode() + b'" content="' + snapshot.digest.encode() + b'">\n'
    return page.replace(b"</head>", meta + b"</head>", 1)


def _subtree_asset(name: str):
    """Resolve a fenced-subtree asset name to (path, ctype), or None."""
    for prefix, exts in _SUBTREES.items():
        if not name.startswith(prefix):
            continue
        rest = name[len(prefix):]
        if "/" in rest or not _SEGMENT_RE.match(rest):
            return None
        for ext, ctype in exts.items():
            if rest.endswith(ext):
                p = (_STATIC / name).resolve()
                try:
                    p.relative_to(_STATIC.resolve())
                except ValueError:
                    return None
                return (p, ctype)
    return None

_JSON = "application/json; charset=utf-8"


def _repo_root() -> Path:
    from laplace.core.checkout import repo_root as rr   # the serving checkout's owner (the server module held the same object under an old name)
    return rr()


def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key, default)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else default
    return (v or default).strip()


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# THE ONE AUTHORED VIEW-ROSTER (W0.1). This literal is the single source of
# truth for the interface's navigable surfaces: the shell renders its nav from
# ``GET /shared/views`` instead of any hardcoded list, and every downstream
# nav/guide consumer joins against it. Add a surface HERE and it appears in the
# shell; nowhere else declares the nav.
#
# Contract per row: id (stable handle, also the shell's active-view key), title
# (the human label), path (a LIVE route — a row pointing at a 404 is a test
# failure, W0.1 fail-closed), purpose (one line), group (primary strip vs the
# "..." disclosure the W1.1 nav will honour).
#
# Coverage is deliberate: every live surface appears. The navigator PAGE
# (``/navigator``) is retired in W0.3 and so is absent, as is the editor
# (``/editor``). The conceptric surface is served at ``/conceptric`` (W3: the
# route promoted from ``/conceptric2``, which now 301s here). No roster row
# points at ``/network/*`` directly: those routes are data, never a nav
# destination (and, per the W5 shell pass, no longer live at all — killed as
# zero-consumer, scanner.py answers them 410).
#
# ACT5 (the shell pass, 2026-07-21): the primary strip is Dashboard · Project ·
# Storyboard · Artefact · Desk. "Project" is ``pipeline`` relabeled — it still
# points at ``/pipeline`` (the project cockpit page hasn't landed yet; this is
# the roster-row rename his ACT5 spec asked for now, not a new surface). The
# brain-scanner map ROW is removed from the roster entirely (his ruling: it is
# a view of the ENGINE, not of a project's work, and doesn't belong in the nav
# at all — not even behind "More"); the ``/map`` ROUTE keeps serving a typed
# URL, and the self-model navigator revisits this at the coupling trigger.
_VIEWS: list[dict[str, str]] = [
    # THE JOURNEY VOCABULARY (2026-07-22, the final-authorship shell): titles carry the
    # process verbs the nav spine speaks — Home · Grow · Shape · Read · Judge · Machine ·
    # Desk — so the nav, the context header, and the stage cards speak ONE language
    # (a crossing feels like turning your head, never changing rooms). The old surface
    # nouns live on in each purpose line. `group` is retired as a nav driver (the journey
    # in _JOURNEY places every row); kept on rows only for downstream joins.
    {"id": "dashboard", "title": "Home", "path": "/", "group": "primary",
     "purpose": "every paper at a glance — where each one stands, its one next action, "
                "and the door to a new project"},
    {"id": "conceptric", "title": "Grow", "path": "/conceptric", "group": "primary",
     "purpose": "the growth cockpit — the goal, the ladder, tensions, coverage, and the "
                "four-verb decisions; the stock map stays a door at /conceptric/map"},
    {"id": "storyboard", "title": "Shape", "path": "/storyboard", "group": "primary",
     "purpose": "the manuscript's spine as a board — the sections, their weight and order, "
                "planned and edited in place"},
    # W2: Projection + Review CONSOLIDATED into the ONE artefact surface — three modes
    # (read / annotate / edit) of one pane set over the shared model (conception §2).
    {"id": "artefact", "title": "Read · Judge", "path": "/artefact", "group": "primary",
     "purpose": "the paper itself — read the current or any version, annotate, rule on "
                "findings, and edit, in one place"},
    # The Machine surface's row keeps its /pipeline label (the pinned handle), but the
    # bare page 301s to the canonical cockpit at /project (scanner.py; contract/
    # tombstones.yaml '/pipeline 301s HERE'). `served` names that landing so the chrome
    # (activeView, viewForPath, the context header, you-are-here, the arrival echo, the
    # tour) resolves the served path and lights this stage — the roster and the served
    # page agree without repathing the row. Add-only: `path` stays /pipeline.
    {"id": "pipeline", "title": "Machine", "path": "/pipeline", "served": "/project",
     "group": "primary",
     "purpose": "the release chain, organ by organ — dials edited in place, a dry-run "
                "preview of what would fire before any commitment"},
    # W5: THE DESK COCKPIT — every decision expands in place into a cockpit (context +
    # consequences + tools + deep-links). The desk MECHANISM rehoused out of the dead /guide
    # explainer (conception §2, §6); it joins the PRIMARY strip (his worklist is first-class).
    {"id": "desk", "title": "Desk", "path": "/desk", "group": "primary",
     "purpose": "every decision that waits on you, each opening into its full cockpit — "
                "context, consequences, tools — in place"},
    # W7: THE ASSET SURFACE — every derivation and every figure an ADDRESSABLE OBJECT OF
    # WORK (THE FAILURE RECORD's debt paid).
    # THE REDLINE WALK (2026-08-10, DESIGN_2026-08-10_the-redline-walk.md). A door under
    # Read · Judge, beside Assets: the same paper, read as CONTENT rather than as the
    # typeset face, with the deposit loop at every altitude. It is a CLEAN-ROOM surface —
    # it imports no shell chrome and carries its own CSS (the clean-room ruling) — so it is
    # rostered as what it is: reachable, named, and off the shell's palette by design.
    {"id": "walk", "title": "Walk", "path": "/walk", "group": "more", "clean_room": True,
     "purpose": "the redline walk — the paper as content-faithful blocks, rewrites typed "
                "straight over the passage, notes and structural verdicts deposited at "
                "every altitude, the typeset pdf one door away"},
    {"id": "assets", "title": "Assets", "path": "/assets", "group": "more",
     "purpose": "every derivation and every figure an addressable object — the rendered figure "
                "or the derivation steps, step/panel-anchored assessment, the banked-edit door, "
                "manifest-only regen; its landings in the reader, its nodes in the conceptric"},
    {"id": "analytics", "title": "Analytics", "path": "/analytics", "group": "more",
     "purpose": "cross-project convergence rollup and per-project round series — honest "
                "about never-run"},
    {"id": "altitude", "title": "Altitude", "path": "/altitude", "group": "more",
     "purpose": "one substrate at rising altitudes — nodes, grade-shells, spine, plan, "
                "prose; the read-only network instrument"},
    # W-guide (2026-07-22, PRM-20260721-structural-guide): the structural account, served
    # ON the interface — his ruling. Renders FROM the operating contract so it cannot drift.
    {"id": "guide", "title": "Guide", "path": "/guide", "group": "more",
     "purpose": "what the engine is, what each surface does, and what every action will "
                "do — the structural guide, rendered from the operating contract"},
    # W-lineage (2026-07-22, PV-20260722T224720Z): the conceptric and its descendants for one
    # paper, on a dedicated surface. A door under Grow (the conceptric's home) — a different
    # lens on the same graph the growth cockpit grows, showing how it descends into the paper.
    {"id": "lineage", "title": "Lineage", "path": "/lineage", "group": "more",
     "purpose": "the conceptric and its descendants for one paper — a lineage-health brief, "
                "then node-outward, object-backward, and whole-graph views of how each concept "
                "links across the map into the manuscript"},
]


def views_roster() -> dict[str, Any]:
    """The one authored roster of interface views (see ``_VIEWS``). Returned as a
    fresh copy so no caller can mutate the source of truth."""
    return {"views": [dict(v) for v in _VIEWS]}


# ---------------------------------------------------------------------------
# THE JOURNEY (the process spine, 2026-07-22 — the final-authorship shell).
#
# The nav stops being an inventory of surface names: the shell renders the
# PROCESS a paper walks — Grow → Shape → Read · Judge → Machine — flanked by
# Home and Desk. Each stage is a roster view promoted to its place in the flow;
# the former "More" rows become DOORS carried by the stage they serve (the map
# under Grow, altitude under Shape, assets under Read, analytics under Machine,
# the guide under Home). The roster (_VIEWS) stays the truth of WHAT exists;
# this literal is the truth of HOW the process flows. Coverage is a law: every
# roster row appears exactly once below, as a stage or as a door — a row left
# out is unreachable and fails the nav test by construction.
#
# ``journey_payload(corpus)`` joins this literal against the roster and, when a
# project is in view, composes ONE live state word per stage server-side (the
# composition law: the client renders these words verbatim, it never
# reconstructs meaning from counts). No corpus → the same spine with no state
# claims (the resting-state law: presence earned by relevance).
_JOURNEY: list[dict[str, Any]] = [
    {"id": "home", "view": "dashboard", "stage": "Home", "flank": True,
     "doors": [{"view": "guide"}]},
    {"id": "grow", "view": "conceptric", "stage": "Grow",
     "doors": [{"title": "the stock map", "path": "/conceptric/map",
                "purpose": "the graded descent — read, audit, and quarry the stock"},
               {"view": "lineage"}]},
    {"id": "shape", "view": "storyboard", "stage": "Shape",
     "doors": [{"view": "altitude"}]},
    {"id": "read", "view": "artefact", "stage": "Read · Judge",
     "doors": [{"view": "walk"}, {"view": "assets"}]},
    {"id": "machine", "view": "pipeline", "stage": "Machine",
     "doors": [{"view": "analytics"}]},
    {"id": "desk", "view": "desk", "stage": "Desk", "flank": True, "doors": []},
]


def _journey_words(corpus: str, root: Path) -> dict[str, dict[str, Any]]:
    """One live, server-composed state phrase per stage for ONE project — plain
    outcome words, the same producers the surfaces themselves read (the counts
    law: a word carrying a count equals what its surface will show). Every read
    degrades to an absent word, never a 500 — a stage without a truth to speak
    stays silent rather than guessing."""
    out: dict[str, dict[str, Any]] = {}
    # GROW — the ladder rung + the open tensions (the cockpit brief's producers).
    try:
        from laplace.web import growth_surface as _gs
        from laplace.pipeline import growth as _growth
        g = _growth.growth_state(root, corpus) or {}
        tensions = len(_gs.all_tensions(root, corpus))
        if tensions:
            word = f"{tensions} tension{'s' if tensions != 1 else ''} to rule"
        elif g.get("present") and g.get("state"):
            word = str(g["state"]).lower().replace("_", " ")
        elif g.get("pre_ladder"):
            word = "grown before the ladder"
        else:
            word = "not seeded yet"
        out["grow"] = {"word": word, "ask": bool(tensions)}
    except Exception:  # noqa: BLE001 — a degraded read is a silent stage, never a crash
        pass
    # SHAPE — the planned spine, plus the open respine intent when one waits on him.
    try:
        respine = None
        try:
            from laplace.pipeline import project_state as _ps
            v = _ps.project_verdict(root, corpus)
            respine = ((v or {}).get("generations") or {}).get("respine_intent")
            out["_verdict"] = {"word": position_words(v), "ask": False}
            # DESK — the decisions this project owes you (project_state.owed_to_author,
            # the same set the desk brief and badge count), so the flank speaks its
            # visit-relevant number on every surface, not only on the desk itself. A
            # project owing nothing stays silent (the resting-state law).
            owed = len((v or {}).get("owed_to_author") or [])
            if owed:
                out["desk"] = {"word": ("1 decision waits" if owed == 1
                                        else f"{owed} decisions wait"), "ask": True}
        except Exception:  # noqa: BLE001
            v = None
        p = registry.plan_path_for(corpus)
        if respine:
            out["shape"] = {"word": "a respine waits on you", "ask": True}
        elif p is not None:
            plan = json.loads(p.read_text(encoding="utf-8"))
            n = len(list(plan.get("sections") or []) + list(plan.get("appendices") or []))
            out["shape"] = {"word": f"{n} sections planned", "ask": False}
        else:
            out["shape"] = {"word": "no plan yet", "ask": False}
    except Exception:  # noqa: BLE001
        pass
    # READ · JUDGE — is there a compiled artefact to stand in front of?
    try:
        from laplace.pipeline import registry as _reg
        ctx = _reg.project_context(corpus, root)
        art = (ctx.current_artefact or {}) if ctx is not None else {}
        if art.get("pdf"):
            kind = str(art.get("kind") or "")
            word = ("a minted release up" if kind in ("clean", "release")
                    else "a candidate up" if kind == "candidate" else "a working copy up")
            out["read"] = {"word": word, "ask": False}
        else:
            out["read"] = {"word": "nothing compiled yet", "ask": False}
    except Exception:  # noqa: BLE001
        pass
    # MACHINE — the truth-layer position words (the same pill the chrome wears).
    mv = out.pop("_verdict", None)
    if mv and mv.get("word"):
        out["machine"] = {"word": mv["word"], "ask": False}
    return out


def journey_payload(corpus: str | None) -> dict[str, Any]:
    """The composed process spine the shell renders as its nav. Stages join the
    roster rows by view id; with a resolvable project in view each stage carries
    its live state word (:func:`_journey_words`). An unknown corpus renders the
    spine without state claims rather than a dead nav."""
    by_id = {v["id"]: v for v in _VIEWS}
    words: dict[str, dict[str, Any]] = {}
    live = False
    if corpus:
        if registry.resolve(corpus) is not None:
            live = True
            words = _journey_words(corpus, _repo_root().resolve())
    stages = []
    for st in _JOURNEY:
        row = by_id.get(st["view"], {})
        w = words.get(st["id"]) or {}
        doors = []
        for d in st["doors"]:
            if "view" in d:
                dr = by_id.get(d["view"], {})
                doors.append({"view": d["view"], "title": dr.get("title", d["view"]),
                              "path": dr.get("path", "/"), "purpose": dr.get("purpose", "")})
            else:
                doors.append({"view": None, "title": d["title"], "path": d["path"],
                              "purpose": d.get("purpose", "")})
        stages.append({
            "id": st["id"], "stage": st["stage"], "view": st["view"],
            "flank": bool(st.get("flank")),
            "path": row.get("path", "/"), "purpose": row.get("purpose", ""),
            "word": w.get("word"), "ask": bool(w.get("ask")),
            "doors": doors,
        })
    return {"corpus": corpus or None, "live": live, "stages": stages}


def humanize_state(s: Any) -> str:
    """The shared composed-word mapping (finding 2, the polish sweep) — a raw pipeline state
    enum (``UNDER_CONVERGENCE`` / ``NEVER_RUN`` / ``RELEASED``) becomes the plain outcome
    words the surfaces speak (``under convergence`` / ``never run`` / ``released``); prose
    that is already composed (``pre-release · GEN-3``) is returned untouched. This is the
    server-side twin of the dashboard's ``low()`` (lowercase + underscore→space), lifted
    here so every stage word, the L1 pill and the analytics state cell run through a single
    mapping and no surface leaks a screaming caps token. Only a wholly upper-case token is
    folded — a mixed-case phrase (which is already human) passes through."""
    t = str(s or "").strip()
    if t and t == t.upper() and any(ch.isalpha() for ch in t):
        return t.lower().replace("_", " ")
    return t


def position_words(verdict: dict[str, Any] | None) -> str:
    """ACT 1 — The one producer of the chrome/roster position label, from a
    :func:`project_state.project_verdict`. The compact head of ``verdict.position``
    (the clause before ``" — "``) plus the generation tag, so the L1 header pill and
    the analytics state cell render the SAME words the dashboard card's position shows
    — ``"pre-release · GEN-3"`` where the card reads ``"pre-release — GEN-3, r2 minted
    2026-07-21"`` — and the chrome can NEVER read the raw ``NEVER_RUN`` state beside a
    project the truth layer knows is pre-release. The head runs through
    :func:`humanize_state`, so a verdict whose ``position`` is itself a bare enum
    (``UNDER_CONVERGENCE``) composes to plain words rather than leaking the raw token.
    Returns ``""`` for an absent/empty verdict (a genuine scaffold), and the caller
    falls back to the raw state."""
    if not verdict or not verdict.get("present"):
        return ""
    pos = (verdict.get("position") or "").strip()
    if not pos:
        return ""
    head = humanize_state(pos.split(" — ", 1)[0].strip())
    gen = (verdict.get("generations") or {}).get("gen")
    if gen and gen not in head:
        head = f"{head} · {gen}"
    return head








# ═══════════════════════════════════════════════════════════════════════════
# W1.2 — THE STALENESS CONTRACT.  ``GET /shared/staleness[?corpus=]`` returns,
# per DERIVED READ the surfaces consume, a uniform verdict
# ``{id,label,scope,present,fresh,reason,producer,built_ts,fix,degraded}``. The
# ``.hy-stale`` atom (static_shared/shell.js + hymn.css) renders it uniformly —
# the ONE stale-banner idiom that replaces the per-page variants each surface
# grew (review's #stale, storyboard's #sb-stale, altitude's plan/prose badge).
#
# The full set of derived reads, reconstructed from those existing banners:
#   * nodemap      (per corpus) — review's node→region map (source-fingerprint gated)
#   * plan→prose   (per corpus) — storyboard's materialised projection (dirty_report)
#   * router cache (global)     — the tracked int8 self-embeddings the router reads
#   * metric       (global)     — the learned bilinear metric distilled over them
#   * voice store  (global)     — the sealed voice-exemplar embeddings the wash reads
#
# HARD LAW (PSU): this endpoint is PURE READS — it stats files, hashes source, and
# reads small JSON. It NEVER fires a rebuild; the ``fix`` field only NAMES the
# deliberate gesture (a command/button), so firing stays the author's to make.
# DEGRADED is a derived flag: a read is degraded when absent OR stale, and a
# surface consuming it says so through the atom.

_MISSING = object()






def _read_row(rid: str, label: str, scope: str, *, present: bool, fresh: bool,
              reason: str | None, producer: str, fix: str,
              built_ts: str | None) -> dict[str, Any]:
    """One derived-read verdict in the uniform shape the ``.hy-stale`` atom renders.
    ``fresh`` is True ONLY when the read is both present AND up to date; ``degraded``
    (absent OR stale) is what a consuming surface reports through the atom."""
    present = bool(present)
    fresh = bool(present and fresh)
    return {
        "id": rid, "label": label, "scope": scope,
        "present": present, "fresh": fresh,
        "reason": (None if fresh else reason),
        "producer": producer, "built_ts": built_ts, "fix": fix,
        "degraded": (not present) or (not fresh),
    }


def read_router_cache(root: Path) -> dict[str, Any]:
    """The tracked int8 router cache (``.self_embeddings.json``): present iff on disk,
    fresh iff not older than the graded network it embeds (``.self_graded.json``). The
    serving path self-heals stale nodes within ``LAPLACE_EMBED_BUDGET``; this only reports."""
    from laplace.representation import embed_router as er
    from laplace.engine.keeper import GRADED_LOCAL
    cache = root / er.CACHE_FILE
    # WO-20260715-233320-psu-embed-off: the LOCAL serving path never embeds (LAPLACE_EMBED_BUDGET=0),
    # so the old "self-heals within budget" wording was a falsehood the PSU law directly contradicts.
    # The warm now runs REMOTE or at the supervised close deposit; the chip surfaces this truthfully.
    producer = "the remote fold or the supervised close deposit (embed_router bulk fold)"
    fix = ("re-embed at the supervised close (`sew up`) or on the remote; the local serving path "
           "never embeds (PSU law: WO-20260715-233320-psu-embed-off)")
    if not cache.is_file():
        return _read_row("router_cache", "router cache", "global", present=False, fresh=False,
                         reason="no embedding cache on disk — routing falls back to lexical",
                         producer=producer, fix=fix, built_ts=None)
    bt = _mtime(cache)
    gt = _mtime(root / GRADED_LOCAL)
    fresh = gt is None or (bt is not None and bt >= gt)
    return _read_row("router_cache", "router cache", "global", present=True, fresh=fresh,
                     reason="the graded network (.self_graded.json) is newer than the cache — "
                            "semantic rank is off until the warm runs remote or at the supervised "
                            "close deposit (the local serving path never embeds)",
                     producer=producer, fix=fix, built_ts=_iso(bt))


def read_self_graph(root: Path) -> dict[str, Any]:
    """The banked graded self-tree (``.self_graded.json``): the identity network the
    ROSTER surfaces consume through ``conceptric.load_network`` (the map, the conceptric
    view, every reconstruct on the serving path). Present iff on disk; when ABSENT the
    serving path degrades to the cheap dir-parent-only network (stamped ``degraded``,
    NEVER the spectral rebuild — RW-20260711-104729) — a real degrade that, until W6.3,
    named nothing on any surface. This row is the escapee W6.3 folded into the census so
    the degrade stops being silent. Freshness is PRESENCE-ONLY by design (the same known
    gap localstate.json names for conceptric-banked-tree: a repo-wide mtime sweep to prove
    freshness costs close to the rebuild itself, so staleness is not asserted here)."""
    from laplace.engine.keeper import GRADED_LOCAL
    tree = root / GRADED_LOCAL
    producer = "laplace.engine.keeper (the graded self-tree, re-embedded at the close deposit)"
    fix = "rebuild the graded tree: `python -m laplace.engine.keeper` (or scripts/reembed.py) — the close deposit"
    if not tree.is_file():
        return _read_row("self_graph", "graded self-tree", "global", present=False, fresh=False,
                         reason="no banked graded tree on disk — the map/conceptric serve the "
                                "cheap dir-parent-only network WITHOUT meaning clustering",
                         producer=producer, fix=fix, built_ts=None)
    return _read_row("self_graph", "graded self-tree", "global", present=True, fresh=True,
                     reason=None, producer=producer, fix=fix, built_ts=_iso(_mtime(tree)))


def read_metric(root: Path) -> dict[str, Any]:
    """The learned bilinear metric (``.metric_M.npz``): present iff on disk, fresh iff not
    older than the router embeddings it was distilled over. Absent → the neutral metric."""
    from laplace.representation import embed_router as er
    metric = root / er.METRIC_FILE
    producer = "metric_distill (learns the bilinear M over the router embeddings)"
    fix = "re-distill the metric (metric_distill) at the next close"
    if not metric.is_file():
        return _read_row("metric", "learned metric", "global", present=False, fresh=False,
                         reason="no trained metric on disk — routing uses the neutral (identity) metric",
                         producer=producer, fix=fix, built_ts=None)
    bt = _mtime(metric)
    et = _mtime(root / er.CACHE_FILE)
    fresh = et is None or (bt is not None and bt >= et)
    return _read_row("metric", "learned metric", "global", present=True, fresh=fresh,
                     reason="the router embeddings are newer than the metric — "
                            "M was distilled over an older embedding set",
                     producer=producer, fix=fix, built_ts=_iso(bt))


def read_voice_store(root: Path) -> dict[str, Any]:
    """The sealed voice-exemplar store (``corpus_stores/voice_corpus_cache/exemplar_passages/``):
    present iff both ``passages.jsonl`` and ``embeddings.json`` exist, fresh iff every
    passage's content hash is embedded (the ``load_store`` sync check, without the numpy load)."""
    store = root / "corpus_stores" / "voice_corpus_cache" / "exemplar_passages"
    pj, ej = store / "passages.jsonl", store / "embeddings.json"
    producer = "voice_corpus_ingest ingest (chunks committed .tex, embeds, seals the store)"
    fix = "python -m laplace.engine.voice_corpus_ingest ingest --rebuild"
    if not (pj.is_file() and ej.is_file()):
        return _read_row("voice_store", "voice store", "global", present=False, fresh=False,
                         reason="no voice store on disk — the wash has no authored exemplars to retrieve",
                         producer=producer, fix=fix, built_ts=None)
    bt = _iso(_mtime(ej))
    try:
        shas = [json.loads(line).get("sha256")
                for line in pj.read_text(encoding="utf-8").splitlines() if line.strip()]
        items = (json.loads(ej.read_text(encoding="utf-8")) or {}).get("items", {})
    except (OSError, json.JSONDecodeError) as e:
        return _read_row("voice_store", "voice store", "global", present=True, fresh=False,
                         reason=f"store unreadable ({e})", producer=producer, fix=fix, built_ts=bt)
    missing = [s for s in shas if s not in items]
    return _read_row("voice_store", "voice store", "global", present=True, fresh=not missing,
                     reason=f"{len(missing)} passage(s) unembedded — the store is out of sync",
                     producer=producer, fix=fix, built_ts=bt)


def read_nodemap(md: Path | None) -> dict[str, Any]:
    """The review surface's node→region map for one manuscript dir. Reuses
    ``review_surface.nodemap_state`` (source-fingerprint gated, no compile) verbatim so the
    contract stays the one truth; ``md`` None (unresolved corpus) reports plainly absent."""
    producer = "the instrumented nodemap build (nodemap.build_nodemap)"
    # /review is a 301 tombstone (Wave 0) — the rebuild affordance lives in the artefact
    # reader's version rail (banked, offer-never-fire; POST /review/rebuild stays the door)
    fix = "rebuild the instrumented map — banked from the artefact reader's version rail"
    if md is None:
        return _read_row("nodemap", "node→region map", "corpus", present=False, fresh=False,
                         reason="no manuscript resolved for this corpus",
                         producer=producer, fix=fix, built_ts=None)
    from laplace.manuscript import review_surface as rv
    st = rv.nodemap_state(md)
    present = bool(st.get("present"))
    built = st.get("built") or _iso(_mtime(md / "main.nodemap.json"))
    return _read_row("nodemap", "node→region map", "corpus", present=present,
                     fresh=bool(st.get("fresh")), reason=st.get("stale_reason"),
                     producer=producer, fix=fix, built_ts=built)


def read_plan_prose(report: list[dict] | None, target_mtime: str | None = None) -> dict[str, Any]:
    """The storyboard's materialised plan→prose projection. ``report`` is
    ``storyboard.dirty_report(corpus)`` (node-set diff per section, no tokens/compile):
    None = corpus unresolved (absent), [] = no sections (present+fresh), any dirty = stale."""
    producer = "the storyboard rebuild (plan → prose, incremental on the % NODES join key)"
    fix = "review the source against its plan; apply authored-source changes through the guarded manuscript workflow. Storyboard work prepares briefs; cheap regeneration is derived-only."
    if report is None:
        return _read_row("plan_prose", "plan → prose", "corpus", present=False, fresh=False,
                         reason="no projection plan resolved for this corpus",
                         producer=producer, fix=fix, built_ts=None)
    n_dirty = sum(1 for r in report if r.get("dirty"))
    return _read_row("plan_prose", "plan → prose", "corpus", present=True, fresh=(n_dirty == 0),
                     reason=f"{n_dirty} section(s) stale — the prose no longer matches the plan",
                     producer=producer, fix=fix, built_ts=target_mtime)


def staleness(corpus: str = "", repo_root: Path | None = None) -> dict[str, Any]:
    """The staleness read-model: every derived read the surfaces consume, each with its
    ``{present,fresh,reason,producer,built_ts,fix,degraded}`` verdict. Global reads always
    ride; the two per-corpus reads (nodemap, plan→prose) ride only when a corpus is named.
    PURE READS — never a rebuild (the PSU law)."""
    root = (repo_root or _repo_root()).resolve()
    reads = [read_self_graph(root), read_router_cache(root), read_metric(root),
             read_voice_store(root)]
    if corpus:
        md = None
        try:
            from laplace.manuscript import review_surface as rv
            md = rv.manuscript_dir(corpus)
        except Exception:
            md = None
        reads.append(read_nodemap(md))
        report = None
        target_mtime = None
        try:
            if registry.plan_path_for(corpus) is not None:
                from laplace.manuscript import storyboard as sb
                report = sb.dirty_report(corpus)
                if md is not None:
                    target_mtime = _iso(_mtime(md / "main.tex"))
        except Exception:
            report = None
        reads.append(read_plan_prose(report, target_mtime))
    return {
        "corpus": corpus or None,
        "reads": reads,
        "degraded": sum(1 for r in reads if r["degraded"]),
        "generated_ts": _iso(_time.time()),
    }


# ═══════════════════════════════════════════════════════════════════════════
# W3.1 — THE VERSIONS JOIN.  ``GET /shared/versions?corpus=`` returns, per project,
# ONE ts-ordered history joining the banked evidence into one legible rail (each row:
# ``{kind, id, ts, label, paths (repo-relative), state}``):
#
#   * ``editor-save`` — a banked editor save in ``editor_saves/`` (W8/J4: every save of
#                    an editor copy banks a VERSION; see ``_editor_save_rows``). LIVE now.
#   * ``snapshot`` — a banked manuscript state in ``versions/`` (hand-placed today;
#                    W3.2 gives ``versions_dir`` its one writer). id/label = dir name.
#   * ``round``    — a fixedpoint round, read through the ONE assembler
#                    (``convergence_ledger.assemble_ledger``) so BOTH layouts join:
#                    the ``rounds/harnessed`` evidence + its ``incumbent_r*`` /
#                    ``lock_r*`` snapshots, AND the older ``judge_rounds/*round*``.
#   * ``release``  — a finalized / bundled / minted release object
#                    (``release/finalize.json`` + ``release/bundle_r*.json`` + the
#                    minted ``*-YYYY-MM-DD-rN.pdf`` at the manuscript top level),
#                    carrying the live release-state-machine ``state``.
#
# HONESTY (repair F10's contract, THE distinction): a project the machine never
# touched returns an HONEST EMPTY (``rows=[]``, ``never_run=True``) — never a
# fabricated row; a ``versions/`` dir that EXISTS but holds no snapshots says so
# (``sources.snapshots.present`` True + ``empty`` True), distinct from one that
# never existed. ``/analytics`` survives as a FIRST-CLASS CONSUMER of this join for
# its history cells — its never-run rendering stays its own; the join is the source,
# not the page (it is never folded into the rail).
#
# BOUNDED (the golden law): the payload is ≤16KB PER PROJECT, ENFORCED at the tail
# (not asserted) — the OLDEST rows shed with a LOUD ``truncated`` flag + ``omitted``
# count, never a silent drop; ``counts`` stay the honest discovered totals.
#
# PURE READS (PSU law): stats dirs, reads small JSON, never writes, never builds.

























#: the row kinds the rail join orders together. ``editor-save`` (W8/J4, LIVE via
#: ``_editor_save_rows``: ``{ts, author, surface, version_id}`` carried alongside the rail
#: contract) rides the same ts-sort + 16KB budget as any other — the join never filters by
#: kind, so a new kind joins by writing rows, never by editing the sort/budget.
_ROW_KINDS = ("snapshot", "round", "release", "editor-save")








def handle(path: str, query: dict, *, snapshot: AssetSnapshot | None = None) -> tuple[int, str, bytes] | None:
    """Route one ``GET /shared/*`` request. Returns (status, content_type,
    body) or None when the path is not ours (the scanner falls through)."""
    if not path.startswith("/shared/"):
        return None
    name = path[len("/shared/"):]

    if name == "views":
        # THE ONE AUTHORED VIEW-ROSTER (W0.1): the shell renders its nav from here.
        return _json_resp(200, views_roster())

    if name == "journey":
        # THE JOURNEY: the process spine with one live state word per stage,
        # composed server-side. Pure reads; no corpus (or an unknown one) serves
        # the spine without state claims rather than an empty nav.
        return _json_resp(200, journey_payload(_q1(query, "corpus") or None))

    if name == "staleness":
        # W1.2 THE STALENESS CONTRACT: per derived read, an honest freshness verdict.
        # PURE READS — never fires a rebuild (the fix field names the gesture instead).
        corpus = _q1(query, "corpus")
        return _json_resp(200, staleness(corpus))

    if name == "plan":
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        out = plan_payload(corpus)
        if out is None:
            return _json_resp(404, {"error": f"no projection plan for corpus {corpus!r}"})
        return _json_resp(200, out)

    if name == "versions":
        # W3.1 THE VERSIONS JOIN: snapshots + rounds (both layouts) + release history,
        # ts-ordered, honest-empty on never-run, bounded to the golden law. Pure reads.
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        out = versions_payload(corpus)
        if out is None:
            return _json_resp(404, {"error": f"no project for corpus {corpus!r}"})
        return _json_resp(200, out)

    if name == "ladder":
        # WAVE 0.5 THE LADDER: six rungs over one target (concept·argument·prose·evidence·
        # judgment·machine), each with an honest count + door, honest absence naming its
        # fix, honest staleness. Pure reads on the cached network. The corpus is fenced
        # via registry.resolve BEFORE any disk touch; an unresolvable TARGET is a 200 with
        # target.known:false (a helpful panel), never a dead end.
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        if registry.resolve(corpus) is None:
            return _json_resp(404, {"error": f"no project for corpus {corpus!r}"})
        from laplace.web import ladder
        out = ladder.ladder_payload(corpus, _q1(query, "target"), _q1(query, "kind"))
        if out is None:
            return _json_resp(404, {"error": f"no project for corpus {corpus!r}"})
        return _json_resp(200, out)

    if snapshot is not None:
        entry = snapshot.assets.get(name)
        if entry is None:
            return _json_resp(404, {"error": f"shared asset {name!r} is not in this writing runtime"})
        return 200, entry[0], entry[1]
    ctype = _ASSETS.get(name)
    if ctype is None:
        sub = _subtree_asset(name)    # fenced subtrees (katex fonts)
        if sub is None:               # unknown name = 404; traversal never touches disk
            return _json_resp(404, {"error": f"unknown shared asset {name!r}"})
        p, ctype = sub
        if not p.is_file():
            return _json_resp(404, {"error": f"shared asset {name!r} missing on disk"})
        return 200, ctype, p.read_bytes()
    p = _STATIC / name
    if not p.is_file():
        return _json_resp(404, {"error": f"shared asset {name!r} missing on disk"})
    return 200, ctype, p.read_bytes()
