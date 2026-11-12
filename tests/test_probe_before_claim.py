"""The probe-before-claim structural guard (scripts/audit_probe_before_claim.py).

The 2026-07-16 class (RW-20260716-144235-142690): a subagent's hedge about
environmental state entered a plan unprobed and outranked banked wake state. The
guard enforces the convention: an environmental claim in a plan-class document
cites a probe in the same paragraph or is flagged.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_probe_before_claim.py"
spec = importlib.util.spec_from_file_location("audit_probe_before_claim", SCRIPT)
apc = importlib.util.module_from_spec(spec)
sys.modules["audit_probe_before_claim"] = apc
spec.loader.exec_module(apc)


def test_unprobed_absence_claim_is_flagged():
    """The founding instance: 'absent-on-remote' with no probe = one finding."""
    text = "## Risks\n\nThe nodemaps are absent-on-remote, so the plan skips them.\n"
    findings = apc.scan_text(text, "ARMING_test.md")
    assert len(findings) == 1
    assert findings[0][0] == "ARMING_test.md" and "absent-on-remote" in findings[0][2]


def test_probed_claim_passes_via_the_typed_marker():
    """[probed: ...] in the paragraph clears the claim."""
    text = ("## Risks\n\nThe nodemaps are absent-on-remote "
            "[probed: git ls-files '*.nodemap.json' -> 0 rows].\n")
    assert apc.scan_text(text) == []


def test_probed_claim_passes_via_a_recognizable_probe_ref():
    """A git command or evidence-node citation in the same paragraph also clears
    it — honest citations predating the marker convention stay green."""
    ok = ("The cache is untracked; git status --porcelain shows it.\n\n"
          "The store is missing per localstate entry voice-store.\n\n"
          "The route is not present — see src/laplace/server.py#L120.\n")
    assert apc.scan_text(ok) == []


def test_paragraph_scope_no_bleed():
    """A probe in one paragraph never clears a claim in another."""
    text = ("Checked with git ls-files, all tracked.\n"
            "\n"
            "The viewer template does not exist on this branch.\n")
    findings = apc.scan_text(text)
    assert len(findings) == 1 and "does" in findings[0][2]


def test_plain_prose_untouched():
    """Non-environmental prose (no present/absent/tracked assertions) is silent."""
    assert apc.scan_text("The weld voices every fragment.\nThe judges rule blind.\n") == []
