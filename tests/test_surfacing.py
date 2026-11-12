"""P6 of the infra deep-dive: the machinery surfaces by reconstruction. The
engine domain routes operational goals (without stealing content goals), the
operations canon nodes exist and stay fresh against the code that generates
them, and the contracts gate proves every surface's claim executably."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from laplace.pipeline.canon import get_canon
from laplace.pipeline import schema
from laplace.pipeline import verify as vf


# ---------------------------------------------------------------------------
# the router: operational goals reach the engine domain
# ---------------------------------------------------------------------------

def test_operational_goals_route_to_engine():
    c = get_canon()
    for goal in ("build section briefs to dispatch to prose builder agents",
                 "what are the seven gates the projection must pass",
                 "run an evolution to restructure a project",
                 "what are the two ledgers and how do they stay in sync",
                 "propagate a substrate change to the dirty sections"):
        assert c.infer_domain(goal) == "engine", goal


def test_content_goals_keep_their_domains():
    # the anti-theft guard: engine tags are curated narrow, so the goals that
    # routed to content domains before the engine domain existed still do
    c = get_canon()
    assert c.infer_domain("build a talk from the manuscript") == "talks"
    assert c.infer_domain("update the jekyll website") == "web"
    assert c.infer_domain("draft the subset-sum manuscript introduction") == "talks"


# ---------------------------------------------------------------------------
# the operations canon: present, resolvable, fresh
# ---------------------------------------------------------------------------

OPERATIONS_NODES = ("two_ledger_system", "projection_plan_schema", "gate_registry",
                    "pipeline_operators", "briefs_and_dispatch", "restructure_howto")


def test_operations_nodes_resolve():
    c = get_canon()
    for name in OPERATIONS_NODES:
        path, body = c.resolve(f"operations/{name}")
        assert body.strip().startswith("#"), name
        # every node is manifest-registered with engine-routable tags
        meta = (c.manifest.get("wiki") or {}).get(f"operations/{name}")
        assert meta and "pipeline" in meta.get("tags", []), name


def test_rendered_docs_cannot_drift():
    r = subprocess.run(
        [sys.executable, "scripts/render_pipeline_docs.py", "--check"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# claims -> gates
# ---------------------------------------------------------------------------

def test_contracts_gate_is_green():
    r = vf.check_contracts()
    assert r["pass"], json.dumps(r["failing"])
    assert len(r["surfaces"]) == len(schema.OPERATION_CONTRACTS)


def test_contracts_reachability_uses_manifest_tags():
    r = vf.check_contracts()
    assert all(s["reachable"] for s in r["surfaces"])


def test_contracts_rides_the_verify_dispatch():
    r = vf.verify(".", checks=["contracts"])
    assert "contracts" in r["checks"] and "errored" not in r


# ---------------------------------------------------------------------------
# the one thing rides every surface
# ---------------------------------------------------------------------------

def test_orient_carries_the_dispatch_law():
    c = get_canon()
    bundle = c.orient("propagate a substrate change to the dirty sections")
    law = bundle["orchestration"]["dispatch_law"]
    assert "reconstruct(node, goal)" in law and "compile_dispatch" in law


def test_wake_hook_prints_the_one_thing():
    hook = Path(".claude/hooks/session-start.mjs").read_text(encoding="utf-8")
    assert "the one thing: enter by reconstruction" in hook
    assert "never read(file)" in hook


def test_spine_carries_the_pipeline_binding():
    d = json.loads(Path("spine_bindings.json").read_text(encoding="utf-8"))
    b = next(x for x in d["bindings"] if x["name"] == "the-pipeline")
    assert any("scripts/evolve.py" in f for f in b["fire"])
    assert any("restructure" in w for w in b["when"])
