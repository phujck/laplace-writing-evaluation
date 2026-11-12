"""W1 — THE DASHBOARD (surface 1): the read door, the New Project door, and the
shared-model + visual-grammar conformance of the first surface built ON the model.

Three clauses, all stdlib/pure (no browser — the J-walks drive the DOM):

  (data)   GET /dashboard/data is the enriched roster (registry.project_states +
           scaffold flag + openable artefact deep-link + compact staleness offers +
           the ONE next action), bounded to the 16KB first-paint law.
  (door)   POST /dashboard/new validates (slug/path-safe, no collision, template set)
           and BANKS a conceptric scaffold on disk (dirs, seed ledger, plan skeleton,
           registry_projects.json row) with the heavy steps banked as work-orders —
           never fired inline — and cleans up after itself in this hermetic test.
  (grammar) dashboard.html conforms to the visual conception §6: hymn.css is the one
           palette (no color literals in its own <style>), the CSS island is ≤4KB
           layout-only, network routes ONLY through store.fetchJSON, and the page ≤16KB.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import pytest

from laplace.projects import project_creation

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[1] / "src" / "laplace"
_GOLDEN = 16 * 1024


# ── (data) GET /dashboard/data ───────────────────────────────────────────────

def test_dashboard_data_shape_and_enrichment():
    """/dashboard/data returns one enriched row per registered project, each carrying the
    dashboard's card fields; the inventory matches registry.project_states."""
    from laplace.web import dashboard
    from laplace.projects import project_creation
    from laplace.pipeline import registry
    st, ctype, body = dashboard.handle("/dashboard/data", {}, "GET", b"")
    assert st == 200 and "json" in ctype
    obj = json.loads(body)
    names = {p["name"] for p in obj["projects"]}
    assert names == set(registry.all_projects()), "every registered project is a card"
    assert obj["templates"] == ["conceptric"]
    for p in obj["projects"]:
        assert set(p) >= {"name", "kind", "state", "pipeline_position", "rounds_n",
                          "next_action", "scaffold", "live", "latest_artefact",
                          "artefact_href", "staleness"}
        assert p["scaffold"] == (p["state"] == "NEVER_RUN")   # scaffold ⇔ NEVER_RUN
        # A1 — THE TRUTHFUL DOOR: a deep-link is offered iff /review's OWN resolver can
        # ACTUALLY open it (manuscript_dir → target_dir; artefacts → an openable pdf),
        # NEVER on mere registry pdf-presence (the lying-door defect).
        rr = dashboard._review_resolution(p["name"])
        if p["artefact_href"]:
            assert p["artefact_href"] == "/artefact?corpus=" + p["name"].replace(" ", "%20")
            assert rr["openable"], f"{p['name']}: door offered but the artefact surface cannot open it"
        else:
            assert not rr["openable"], f"{p['name']}: the artefact surface can open it but the door is dead"
        # A6 — THE TIER: live iff run (state past NEVER_RUN), or real rounds, or a minted release
        assert p["live"] == ((p["state"] != "NEVER_RUN") or (p["rounds_n"] > 0) or rr["minted"])
        # a scaffold has no derived reads to be stale about (honest empty, not fake-fresh)
        if p["scaffold"]:
            assert p["staleness"] == []
        for chip in p["staleness"]:
            assert set(chip) == {"label", "state", "fix"} and chip["state"] in ("stale", "absent")


def test_dashboard_data_is_within_the_16kb_first_paint_law():
    """The dashboard's one fetch is bounded (conception §8): ≤16KB first paint over the
    LIVE roster — only degraded per-corpus staleness rides, never a per-card alarm wall."""
    from laplace.web import dashboard
    _st, _ct, body = dashboard.handle("/dashboard/data", {}, "GET", b"")
    assert len(body) <= _GOLDEN, f"/dashboard/data {len(body)}B over the 16KB golden"


def test_dashboard_open_orders_render_the_shared_resolution_join(tmp_path):
    """A stored ``status: open`` is raise-time history, never dashboard state."""
    from laplace.web import dashboard
    store = tmp_path / "corpus_friction"
    store.mkdir()
    rows = [
        {"record": "work-order", "id": "WO-live", "corpus": "paper", "status": "open"},
        {"record": "work-order", "id": "WO-done", "corpus": "paper", "status": "open"},
        {"record": "resolution", "id": "RES-done", "consumes": "WO-done",
         "evidence": ["commit:done"]},
    ]
    (store / "work_orders.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    got = dashboard._open_work_orders(tmp_path)
    assert [r["id"] for r in got["paper"]] == ["WO-live"]


def test_dashboard_names_a_poisoned_order_store_as_a_lower_bound(tmp_path):
    from laplace.web import dashboard
    store = tmp_path / "corpus_friction"
    store.mkdir()
    (store / "work_orders.jsonl").write_text(
        json.dumps({"record": "work-order", "id": "WO-live", "corpus": "paper",
                    "status": "open"}) + "\nnot-json\n", encoding="utf-8")
    projection = dashboard._work_order_projection(tmp_path)
    assert [r["id"] for r in projection["by_corpus"]["paper"]] == ["WO-live"]
    integrity = projection["integrity"]
    assert integrity["cracked"] and integrity["count_is_lower_bound"]
    assert integrity["residuals"][0]["line"] == 2


def test_missing_order_store_is_cracked_not_a_clean_zero(tmp_path):
    from laplace.web import dashboard
    projection = dashboard._work_order_projection(tmp_path)
    integrity = projection["integrity"]
    assert projection["by_corpus"] == {}
    assert integrity["cracked"] and integrity["residual_count"] == 1
    assert integrity["residuals"][0]["defect"] == "store-unreadable"


def test_integrity_residuals_yield_before_project_cards_under_byte_budget():
    from laplace.web import dashboard
    handle = "sha256:" + "a" * 64
    payload = {
        "projects": [{"name": "hot", "live": True, "updated": "2026-08-25"}],
        "work_order_integrity": {
            "cracked": True, "residual_count": 1,
            "residuals": [{"error": "x" * 100_000}],
            "residuals_truncated": False, "residuals_omitted": 0,
            "residual_handle": handle,
        },
        "thinned": 0, "truncated": False, "omitted": 0,
    }
    dashboard._enforce_first_paint_budget(payload)
    assert len(json.dumps(payload).encode("utf-8")) <= 16_384
    assert payload["projects"][0]["name"] == "hot"
    integrity = payload["work_order_integrity"]
    assert integrity["residuals"] == [] and integrity["residuals_omitted"] == 1
    assert integrity["residual_handle"] == handle


def test_subset_sum_card_reflects_the_live_state():
    """The enriched roster carries subset-sum-itqde's REAL state (UNDER_CONVERGENCE, 5
    rounds, an openable artefact) — J1's headline, asserted headless."""
    from laplace.web import dashboard
    obj = json.loads(dashboard.handle("/dashboard/data", {}, "GET", b"")[2])
    ss = {p["name"]: p for p in obj["projects"]}["subset-sum-itqde"]
    assert ss["state"] == "UNDER_CONVERGENCE" and ss["rounds_n"] == 5
    assert ss["scaffold"] is False and ss["live"] is True
    assert ss["artefact_href"] == "/artefact?corpus=subset-sum-itqde"
    assert ss["next_action"] == "review candidate"


def test_dashboard_door_is_gated_on_what_the_artefact_surface_can_open():
    """A1 → W2 UNIFICATION: 'open latest' is offered iff the ONE authority
    (registry.project_context) resolves a real current-artefact pdf, never on a plan's
    target_dir guess. qde (no built pdf) is DISABLED; subset-sum-itqde (a live candidate)
    is ENABLED; law-of-laws — whose real main.pdf the plan's target_dir could NOT reach in
    W1 — now resolves through project_context and its door HONESTLY ENABLES (the W2 door A1
    deferred). No open door is a lie — every offered link is one project_context can serve."""
    from laplace.web import dashboard
    obj = json.loads(dashboard.handle("/dashboard/data", {}, "GET", b"")[2])
    door = {p["name"]: p["artefact_href"] for p in obj["projects"]}
    assert door.get("qde") is None, "qde: no built pdf (project_context resolves none) — door must be dead"
    assert door.get("subset-sum-itqde") == "/artefact?corpus=subset-sum-itqde", \
        "subset-sum-itqde has a live candidate — door must be live"
    assert door.get("law-of-laws") == "/artefact?corpus=law-of-laws", \
        "law-of-laws: project_context now reaches its real main.pdf — the W2 door ENABLES"
    for p in obj["projects"]:
        assert bool(p["artefact_href"]) == dashboard._review_resolution(p["name"])["openable"], \
            f"{p['name']}: door disagrees with the unified resolver (a lie survives)"


def test_dashboard_live_tier_promotes_a_rounds_or_minted_paper():
    """A6 — THE TIER: a NEVER_RUN-stated paper with real rounds + a minted release PDF
    (paper_falqon) is LIVE work, not a scaffold shelf card; a genuine bare scaffold (no
    rounds, no artefact) stays on the shelf; a running paper stays live."""
    from laplace.web import dashboard
    obj = json.loads(dashboard.handle("/dashboard/data", {}, "GET", b"")[2])
    by = {p["name"]: p for p in obj["projects"]}
    falqon = by["paper_falqon"]
    assert falqon["scaffold"] is True and falqon["rounds_n"] > 0     # NEVER_RUN-stated, yet has run
    assert falqon["live"] is True, "paper_falqon (rounds + minted release) must render in the live tier"
    assert by["subset-sum-itqde"]["live"] is True
    assert by["website"]["live"] is False and by["website"]["scaffold"] is True   # a true bare scaffold


# ── (door) POST /dashboard/new — validation + scaffold + cleanup ─────────────

def test_new_project_validation_rejects_bad_names_and_collisions():
    """The door is fail-closed: a non-slug name, an unbuilt template, and a collision with
    a registered project are all refused BEFORE any write (no half-scaffold)."""
    from laplace.web import dashboard
    for bad in ("Has Caps", "a", "../escape", "x/y", "trailing-", "", "UPPER"):
        st, obj = project_creation.create_project(bad, "conceptric")
        assert st == 400 and obj["ok"] is False, f"{bad!r} should be a 400"
    st, obj = project_creation.create_project("valid-name", "slides")
    assert st == 400 and "template" in obj["error"]
    st, obj = project_creation.create_project("subset-sum-itqde", "conceptric")   # a real registered project
    assert st == 409 and obj["ok"] is False


def test_new_project_banks_the_full_scaffold_on_disk(tmp_path):
    """The New Project door banks EVERYTHING J6 asserts, in a hermetic tmp root: the
    project dirs, the conceptric seed ledger, the projection_plan skeleton, the
    registry_projects.json data row, and the heavy steps banked as work-orders (never
    fired). Every path the door reports is real on disk."""
    from laplace.web import dashboard
    name = "scratch-project-x"
    st, obj = project_creation.create_project(name, "conceptric", root=tmp_path)
    assert st == 201 and obj["ok"] is True and obj["name"] == name

    # the dirs
    ms = tmp_path / "synthetics papers" / name / "manuscript"
    for d in (ms / "whitepaper" / "feedback", ms / "briefs", ms / "versions", ms / "evolutions"):
        assert d.is_dir(), f"missing scaffold dir {d}"
    # the conceptric SEED ledger (a real, non-empty L1 store)
    ledger = tmp_path / "corpus_friction" / f"{name}.jsonl"
    assert ledger.is_file()
    seed = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert seed["kind"] == "seed" and seed["owning_layer"] == name
    # the projection_plan SKELETON
    plan = json.loads((ms / "projection_plan.json").read_text(encoding="utf-8"))
    assert plan["meta"]["project"] == name and plan["sections"] == [] and plan["appendices"] == []
    # the registry_projects.json DATA ROW
    reg = json.loads((tmp_path / "registry_projects.json").read_text(encoding="utf-8"))
    assert any(r["name"] == name and r["kind"] == "conceptric" for r in reg["projects"])
    # the HEAVY steps banked as work-orders (offer law — named, never fired)
    wos = [json.loads(l) for l in (tmp_path / "corpus_friction" / "work_orders.jsonl")
           .read_text(encoding="utf-8").splitlines() if l.strip()]
    actions = {w["action"] for w in wos if w["corpus"] == name}
    assert actions == {"first-compile", "embeddings-build"}
    assert all(w["status"] == "open" and w["cost_class"] == "expensive"
               for w in wos if w["corpus"] == name)
    # the door reported exactly what it wrote (auditable / reversible)
    assert obj["work_orders"] and len(obj["work_orders"]) == 2
    for rel in obj["created"]:
        assert (tmp_path / rel).exists(), f"reported-created path not on disk: {rel}"


def test_new_project_data_row_merges_into_the_registry(tmp_path, monkeypatch):
    """A banked registry_projects.json row is MERGED by registry._projects as a generic
    conceptric project; a HAND-AUTHORED BLOCK wins on collision (data never shadows a
    declared layout). The collision witness is eigenengine, not subset-sum-itqde: since
    the hardcoded corpus dict retired (2026-08-04) the finished papers ARE data rows, so
    a data row naming one defines it rather than losing to it - the whole point of the
    migration. Only the five hand-authored blocks still outrank data."""
    from laplace.pipeline import registry
    monkeypatch.setattr(registry, "_repo_root", lambda: tmp_path)
    # a fresh data project + a data row colliding with a hand-authored block (must lose)
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [
        {"name": "data-only-proj", "kind": "conceptric",
         "tex_root": "synthetics papers/data-only-proj/manuscript"},
        {"name": "eigenengine", "tex_root": "synthetics papers/SHADOW/manuscript"},
        {"name": "subset-sum-itqde", "tex_root": "synthetics papers/DATA/manuscript"},
    ]}), encoding="utf-8")
    reg = registry.all_projects()
    assert "data-only-proj" in reg, "the data row must register"
    assert reg["data-only-proj"].kind == "conceptric"
    # the hand-authored block wins: eigenengine's declared bare-tex root, not the SHADOW
    assert reg["eigenengine"].tex_root == "eigenengine/manuscript"
    # a migrated paper is ordinary data now - the row defines it, nothing outranks it
    assert reg["subset-sum-itqde"].tex_root == "synthetics papers/DATA/manuscript"


# ── (door, A2) the New Project door under CONCURRENCY ────────────────────────

def _wo_rows(root: Path, name: str) -> list[dict]:
    p = root / "corpus_friction" / "work_orders.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip() and json.loads(l).get("corpus") == name]


def test_concurrent_double_post_same_name_is_deterministic(tmp_path):
    """A2 — the judge's double-POST hammer: two threads race to create the SAME name. The
    project-dir mkdir is the atomic claim, so EXACTLY one wins (201) and the other loses
    (409) — never [201, 201] with a doubled scaffold. Disk state is a single scaffold: one
    registry row, exactly two work-orders (not four). Many trials prove it is deterministic."""
    from laplace.web import dashboard
    for trial in range(12):
        name = f"race-{trial}"
        start = threading.Barrier(2)
        collect = threading.Lock()
        results: list[int] = []

        def worker():
            start.wait()
            st, _obj = project_creation.create_project(name, "conceptric", root=tmp_path)
            with collect:
                results.append(st)

        ts = [threading.Thread(target=worker) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert sorted(results) == [201, 409], \
            f"trial {trial}: want one 201 + one 409, got {sorted(results)}"
        reg = json.loads((tmp_path / "registry_projects.json").read_text(encoding="utf-8"))
        assert sum(1 for r in reg["projects"] if r["name"] == name) == 1, "doubled registry row"
        assert len(_wo_rows(tmp_path, name)) == 2, "the scaffold's work-orders were banked twice"


def test_concurrent_distinct_names_preserve_every_registry_row(tmp_path):
    """A2 — the judge's second hammer: N threads create N DISTINCT names at once. Every row
    survives — the two shared stores (registry_projects.json + work_orders.jsonl) are
    serialised, so the unlocked read-modify-write that lost 7/8 rows can no longer drop one."""
    from laplace.web import dashboard
    n = 8
    names = [f"proj-{i}" for i in range(n)]
    start = threading.Barrier(n)
    collect = threading.Lock()
    results: dict[str, int] = {}

    def worker(nm):
        start.wait()
        st, _obj = project_creation.create_project(nm, "conceptric", root=tmp_path)
        with collect:
            results[nm] = st

    ts = [threading.Thread(target=worker, args=(nm,)) for nm in names]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert all(st == 201 for st in results.values()), f"a distinct create failed: {results}"
    reg = json.loads((tmp_path / "registry_projects.json").read_text(encoding="utf-8"))
    got = {r["name"] for r in reg["projects"]}
    assert set(names) <= got, f"registry lost rows under concurrency: missing {set(names) - got}"
    for nm in names:
        assert len(_wo_rows(tmp_path, nm)) == 2, f"{nm}: work-orders not banked exactly twice"


# ── (grammar) dashboard.html conforms to the visual conception §6 ────────────

def _dashboard_html() -> str:
    return (_SRC / "web" / "dashboard.html").read_text(encoding="utf-8")


def _style_block(html: str) -> str:
    m = re.search(r"<style>(.*?)</style>", html, re.S)
    return m.group(1) if m else ""


def test_dashboard_html_is_within_16kb():
    assert len(_dashboard_html().encode("utf-8")) <= _GOLDEN


def test_dashboard_css_island_is_layout_only_under_4kb_no_color_literals():
    """Visual §6.1/§6.2: the surface links hymn.css (the one palette) and its OWN <style>
    is ≤4KB layout-only with NO color literals — every card/chip/door color rides a hymn
    component class, so the palette cannot re-fork per surface."""
    html = _dashboard_html()
    assert 'href="/shared/hymn.css"' in html, "must link the one palette sheet"
    style = _style_block(html)
    assert len(style.encode("utf-8")) <= 4 * 1024, "the CSS island is over the 4KB budget"
    hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", style)
    funcs = re.findall(r"\b(?:rgb|rgba|hsl|hsla)\(", style)
    assert not hexes and not funcs, f"color literals leaked into the island: {hexes + funcs}"
    # composed from the shared component vocabulary (hymn.css), not bespoke classes
    for cls in ("hy-card", "hy-chip", "hy-door"):
        assert cls in html, f"the dashboard must compose from the shared {cls!r}"


def test_dashboard_routes_all_network_through_the_model():
    """The FIRST rebuilt surface: all network rides store.fetchJSON — no raw fetch(/XHR/
    EventSource escapes the model (the standing clause, proven over the real surface)."""
    html = _dashboard_html()
    assert '/shared/store.mjs' in html and "store.fetchJSON(" in html
    # strip comments, then no raw network idiom survives
    text = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"(?m)//.*$", " ", text)
    assert not re.search(r"\bfetch\s*\(|\bXMLHttpRequest\b|\bEventSource\s*\(", text), \
        "raw network escaped the model on the dashboard"
