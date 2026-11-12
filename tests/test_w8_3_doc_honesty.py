"""W8.3 — the doc honesty sweep: the interface docs' mechanical claims are CHECK lines now.

The sweep folded the interface's mechanically-checkable claims (the roster law, the retired routes,
the desk cap, the 16KB first paint, the co-cited knob, the live-pane poll, the wake verb) into the
run_claim_checks idiom, and extended the runner to scan the live interface docs alongside the
AUDIT_*.md corpus. These pin it FAIL-CLOSED:

  * every CHECK banked into a swept doc is EVALUATED (RUNNABLE), never silently PROSE-classed, and
    over the live tree every one PASSES — so the runner reports VERDICT=PASS with the new checks live;
  * a deliberately falsified interface claim (a scratch doc whose CHECK asserts a symbol the scratch
    code does not carry) FAILs and moves the exit code — the sweep expires a drifted claim loudly;
  * the count of swept CHECK lines is honest: every `CHECK:` line in the interface docs is collected
    and evaluated, none dropped.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "run_claim_checks", ROOT / "scripts" / "run_claim_checks.py"
)
rcc = importlib.util.module_from_spec(_SPEC)
sys.modules["run_claim_checks"] = rcc
_SPEC.loader.exec_module(rcc)

# the swept docs, by the basename collect() stamps on each ClaimCheck.
_DOC_NAMES = {Path(d).name for d in rcc.INTERFACE_DOCS}


def _interface_checks():
    return [c for c in rcc.collect(ROOT) if c.audit in _DOC_NAMES]


def test_interface_docs_are_in_the_scan_roster():
    # the four surfaces the sweep is bounded to.
    assert "interface/FUNCTION_INTERROGATIONS.md" in rcc.INTERFACE_DOCS
    assert "HANDOFF.md" in rcc.INTERFACE_DOCS
    assert "TECHNICAL_GUIDE.md" in rcc.INTERFACE_DOCS
    assert "PIPELINE_GUIDE.md" in rcc.INTERFACE_DOCS


def test_every_swept_check_is_evaluated_not_prose():
    checks = _interface_checks()
    # the sweep landed real checks, not zero.
    assert checks, "no CHECK lines collected from the interface docs"
    # each is a runnable predicate that was actually evaluated — never PROSE-classed.
    for c in checks:
        assert c.kind == "RUNNABLE", f"interface CHECK left PROSE: {c.text!r}"
        assert c.verdict in ("PASS", "EYE"), f"interface CHECK not evaluated PASS/EYE: {c.verdict} {c.text!r}"


def test_swept_checks_all_pass_over_the_live_tree():
    checks = _interface_checks()
    fails = [c for c in checks if c.verdict == "FAIL"]
    assert not fails, f"drifted interface claim(s): {[c.text for c in fails]}"
    # the whole runner (audits + interface docs) does not fail on the interface checks.
    assert all(c.verdict != "FAIL" for c in checks)


def test_count_reported_honestly():
    # every `CHECK:` line physically present in a swept doc is collected — none dropped, none doubled.
    import re
    label = re.compile(r"\bCHECK(?:\s*\([^)]*\))?\s*:")
    banked = 0
    for rel in rcc.INTERFACE_DOCS:
        p = ROOT / rel
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if label.search(line):
                banked += 1
    collected = len(_interface_checks())
    assert collected == banked, f"collected {collected} != {banked} CHECK lines in the docs"
    # the sweep banked a real population (the seven named interface claims, some multi-check).
    assert banked >= 11


def test_falsified_interface_claim_fails_closed(tmp_path, monkeypatch):
    # a scratch repo: the code does NOT carry the claimed endpoint, and the doc asserts it does.
    # the runner must FAIL that check and move the exit code — a drifted claim expiring loudly.
    (tmp_path / "src" / "laplace").mkdir(parents=True)
    (tmp_path / "src" / "laplace" / "web" / "scanner.py").write_text(
        "# a scratch scanner with NO co-cited route\n", encoding="utf-8"
    )
    (tmp_path / "scratch_iface.md").write_text(
        "## scratch surface\n"
        "for him: the co-cited knob.\n"
        "- CHECK: `grep -c '/corpus/co-cited' src/laplace/web/scanner.py` ≥ 1 "
        "— the endpoint exists.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rcc, "INTERFACE_DOCS", ("scratch_iface.md",))
    checks = rcc.collect(tmp_path)
    assert len(checks) == 1
    assert checks[0].kind == "RUNNABLE"
    assert checks[0].verdict == "FAIL", "a falsified interface claim must FAIL, not pass or prose"
    assert rcc.main(["--repo", str(tmp_path)]) == 1  # FAIL moves the exit code


def test_falsified_claim_passes_when_code_carries_it(tmp_path, monkeypatch):
    # the mirror: give the scratch code the route the doc claims, and the SAME check passes — proving
    # the FAIL above is the claim drifting, not the mechanism mis-firing.
    (tmp_path / "src" / "laplace").mkdir(parents=True)
    (tmp_path / "src" / "laplace" / "web" / "scanner.py").write_text(
        'elif u.path == "/corpus/co-cited":\n    ...\n', encoding="utf-8"
    )
    (tmp_path / "scratch_iface.md").write_text(
        "## scratch surface\n"
        "- CHECK: `grep -c '/corpus/co-cited' src/laplace/web/scanner.py` ≥ 1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rcc, "INTERFACE_DOCS", ("scratch_iface.md",))
    checks = rcc.collect(tmp_path)
    assert checks[0].verdict == "PASS"
    assert rcc.main(["--repo", str(tmp_path)]) == 0
