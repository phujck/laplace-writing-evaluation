"""Stage B — the manuscript projection specification (rebuild mandate §5).

The first manuscript-facing artifact: the paper's intellectual contract as
typed objects, complete BEFORE any structural, narrative, or prose work. It
does not duplicate the conceptric — the conceptric IS the typed content-object
store (§5.2's Definition/Claim/Derivation objects are def:/res:/thm:/ds:/irf:
nodes with essences and edges). What this artifact adds is exactly what no
node carries:

- the §5.1 global manuscript record (purpose, scope, non-claims, reader,
  genre, notation + terminology registries, budgets);
- §5.5/§5.6 figure and table SPECIFICATIONS, caption included (the
  four-question caption law is settled here, never improvised by a renderer);
- §5.3 equation-ledger ROLE annotations layered over the nodes' latex_labels.

One artifact: ``<manuscript_dir>/manuscript_spec.json``
(schema.STAGE_ARTIFACTS["spec"]). Validation is §11.1, run by
:func:`validate_spec` and folded into the plan-validation path.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from laplace.pipeline import registry, schema

#: Node-kind → default equation-ledger role (§5.3's structural distinction).
#: Spec entries may override per label.
_KIND_ROLE = {
    "def": "definition",
    "thm": "exact-identity",
    "ds": "derivation-step",
    "irf": "bound",
    "res": "numerical-observation",
}


def spec_path(project: str, repo_root: Path | None = None) -> Path | None:
    proj = registry.resolve(project, repo_root=repo_root) if repo_root is not None else registry.resolve(project, repo_root=repo_root)
    return proj.stage_path("spec", repo_root) if proj else None


def load_spec(project: str, repo_root: Path | None = None) -> dict | None:
    p = spec_path(project, repo_root)
    if p is None or not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # p.is_file() above already confirmed the file exists - corrupt is not absent
        logging.getLogger(__name__).warning(
            "load_spec: %s exists but failed to parse: %s", p, exc)
        return None


def write_spec(project: str, spec: dict, repo_root: Path | None = None) -> Path:
    p = spec_path(project, repo_root)
    if p is None:
        raise ValueError(f"no spec path for project {project!r}")
    update_file(p, lambda _: spec)
    return p


def update_file(path: Path, update) -> dict:
    """Merge one organ's contribution while holding the shared specification lock."""
    revised, _before, _intended = update_file_with_receipt(path, update)
    return revised


def update_file_with_receipt(path: Path, update) -> tuple[dict, bytes | None, bytes]:
    """Update the spec and return the exact preimage and intended postimage.

    The byte identities are captured under the same lock as the canonical write,
    so a caller can issue an ephemeral owner-mutation receipt without inventing a
    second revision ledger.
    """
    from filelock import FileLock
    import uuid
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock", timeout=15):
        before = path.read_bytes() if path.is_file() else None
        current = json.loads(before.decode("utf-8")) if before is not None else {}
        if not isinstance(current, dict):
            raise ValueError("The manuscript specification must be an object.")
        revised = update(current)
        if not isinstance(revised, dict):
            raise ValueError("The updated manuscript specification must be an object.")
        intended = (json.dumps(revised, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        pending = path.with_name(path.name + "." + uuid.uuid4().hex + ".pending")
        pending.write_bytes(intended)
        pending.replace(path)
        return revised, before, intended


def derive_equation_ledger(project: str, repo_root: Path | None = None) -> dict[str, dict]:
    """§5.3 — the equation ledger DERIVED from the conceptric. The house label
    convention is label == node id (display mathematics anchors by the node
    that owns it, never a parallel ``eq:`` namespace), so the ledger is every
    live labelled node of a mathematics-bearing kind, with its role defaulted
    from the kind. The spec's ``equation_ledger`` overrides merge on top, so
    role corrections are authored data, never a parallel store."""
    proj = registry.resolve(project, repo_root=repo_root)
    if proj is None or proj.kind != "conceptric":
        return {}
    from laplace.research import corpus_ingest as ci
    rr = Path(repo_root) if repo_root else registry._repo_root()
    net = ci.corpus_network(ci.resolve_corpus(rr, project), repo_root=rr, name=project)
    # owning section by PLAN MEMBERSHIP (the definitive placement) — a node's
    # section_ref points at its section's anchor BEAT (a node id, the L1
    # mirror's convention), never at a section id, so membership is the join.
    plan = proj.read_plan(repo_root) or {}
    owner: dict[str, str] = {}
    for sec in schema.plan_sections(plan):
        for nid in schema.section_nodes(sec):
            owner.setdefault(nid, sec["id"])
    ledger: dict[str, dict] = {}
    for nid, nd in net["nodes"].items():
        pj = schema.proj_of(nd)
        label = pj.get("latex_label") or ""
        if not label or pj.get("retired"):
            continue
        prefix = nid.split(":", 1)[0]       # ids are the stable kind vocabulary
        if prefix not in _KIND_ROLE:        # fig/ref/fork labels are not equations
            continue
        ledger[label] = {
            "label": label, "node": nid,
            "role": _KIND_ROLE[prefix],
            "section": owner.get(nid, ""),
            "anchor_beat": pj.get("section_ref") or "",
        }
    return ledger


def effective_equation_ledger(project: str, repo_root: Path | None = None) -> dict[str, dict]:
    """Derived ledger + authored overrides from the spec artifact."""
    ledger = derive_equation_ledger(project, repo_root)
    spec = load_spec(project, repo_root) or {}
    for label, entry in (spec.get("equation_ledger") or {}).items():
        ledger.setdefault(label, {"label": label}).update(entry)
    return ledger


def validate_spec(project: str, repo_root: Path | None = None) -> dict[str, Any]:
    """§11.1 projection validation. Mechanical, artifact-local plus the joins
    the plan validator cannot see: figure specs complete and mutually complete
    with the plan, captions settled, the global record filled, terminology
    registered. Claim-support and symbol-order checks live with the conceptric
    gates and the §6.3 structural gate — never duplicated here."""
    proj = registry.resolve(project, repo_root=repo_root)
    if proj is None:
        return {"pass": None, "error": f"unknown project {project!r}"}
    spec = load_spec(project, repo_root)
    if spec is None:
        return {"pass": False, "missing": str(spec_path(project, repo_root))}

    issues: list[dict[str, str]] = []
    record = spec.get("manuscript") or {}
    required = ("manuscript_id", "working_title", "purpose", "primary_contribution",
                "scope", "non_claims", "target_reader", "genre", "notation",
                "terminology")
    for f in required:
        if not record.get(f):
            issues.append({"where": "manuscript", "issue": f"empty field {f!r}"})

    plan = proj.read_plan(repo_root) or {}
    planned_figs = {fid for sec in schema.plan_sections(plan)
                    for fid in (sec.get("figures") or [])}
    spec_figs = spec.get("figures") or {}
    for fid, fs in spec_figs.items():
        for f in ("question_answered", "function", "caption", "status"):
            if not fs.get(f):
                issues.append({"where": fid, "issue": f"figure spec missing {f!r}"})
        if fs.get("status") == "banked" and not (fs.get("generator") or fs.get("data_sources")):
            issues.append({"where": fid,
                           "issue": "banked figure without generator/data_sources"})
    for fid in sorted(planned_figs - set(spec_figs)):
        issues.append({"where": fid, "issue": "planned figure has no spec entry"})
    for fid in sorted(set(spec_figs) - planned_figs):
        issues.append({"where": fid, "issue": "spec figure not planned anywhere"})

    for tid, ts in (spec.get("tables") or {}).items():
        for f in ("question_answered", "row_semantics", "column_semantics", "caption"):
            if not ts.get(f):
                issues.append({"where": tid, "issue": f"table spec missing {f!r}"})

    terms = record.get("terminology") or {}
    if isinstance(terms, dict):
        for term, definition in terms.items():
            if not definition:
                issues.append({"where": f"term:{term}", "issue": "unregistered meaning"})
    if spec.get("schema") == "laplace-manuscript-spec/0.2":
        policy = record.get("nomenclature_policy") or {}
        if not isinstance(policy, dict) or not policy.get("topic_field"):
            issues.append({
                "where": "manuscript.nomenclature_policy",
                "issue": "strict nomenclature requires a topic_field",
            })
        allowed_status = {"field-standard", "prior-literature", "coined-here"}
        for term, entry in terms.items() if isinstance(terms, dict) else ():
            where = f"term:{term}"
            if not isinstance(entry, dict):
                issues.append({
                    "where": where,
                    "issue": "strict nomenclature entry must be a structured record",
                })
                continue
            for field in ("definition", "status", "field", "alternatives"):
                if field not in entry or entry[field] in (None, ""):
                    issues.append({
                        "where": where,
                        "issue": f"strict nomenclature entry missing {field!r}",
                    })
            status = entry.get("status")
            if status and status not in allowed_status:
                issues.append({
                    "where": where,
                    "issue": f"unknown nomenclature status {status!r}",
                })
            alternatives = entry.get("alternatives")
            if alternatives is not None and not isinstance(alternatives, list):
                issues.append({
                    "where": where,
                    "issue": "alternatives must be a list of cross-literature names",
                })
            if status == "coined-here":
                for field in ("novel_concept", "introduced_after"):
                    if not entry.get(field):
                        issues.append({
                            "where": where,
                            "issue": f"coinage missing {field!r}",
                        })

    return {"pass": not issues, "project": project, "issues": issues,
            "n_figures": len(spec_figs), "n_equations":
            len(effective_equation_ledger(project, repo_root))}
