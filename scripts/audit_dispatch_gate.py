"""Static D2 admission audit: every first-party provider edge is gate-dominated."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WORKFLOWS = (
    ".claude/workflows/f-loop-integration.js",
    ".claude/workflows/pipeline-chain-integration.js",
    ".claude/workflows/project-fixedpoint.js",
    ".claude/workflows/project-harnessed.js",
    ".claude/workflows/project-pipeline.js",
    ".claude/workflows/project-staged.js",
    ".claude/workflows/weld-cwave3.js",
    "scripts/wf_closure_test.mjs",
    "scripts/wf_consolidate_lenses.mjs",
    "scripts/wf_fold_person.mjs",
    "scripts/wf_fold_up.mjs",
    "scripts/wf_insert_middle.mjs",
    "scripts/wf_one_person.mjs",
    "scripts/wf_people_sweep.mjs",
    "scripts/wf_promote_node.mjs",
    "scripts/wf_refine_essences.mjs",
    "scripts/wf_structural_shard.mjs",
    "scripts/wf_tranche1_relational.mjs",
    "scripts/wf_upfold_only.mjs",
    "scripts/wf_voice_from_papers.mjs",
    "scripts/wf_wire_tranche2.mjs",
    "scripts/workflows/falqon_phase_b.workflow.mjs",
    "experiments/plateau_falsifier.workflow.js",
    "workflows/hello_fidelity_test.mjs",
    "workflows/hello_generator.mjs",
)
EXPECTED_AGENT_CALLS = 81

SCAN_ROOTS = (".claude/workflows", "scripts", "workflows", "experiments")
SUFFIXES = {".js", ".mjs", ".cjs"}
FORBIDDEN_ALIAS = (
    re.compile(r"globalThis\s*(?:\.agent|\[['\"]agent['\"]\])"),
    re.compile(r"(?:const|let|var)\s+\w+\s*=\s*agent\b"),
    re.compile(r"\b(?:eval|Function)\s*\("),
    re.compile(r"\bagent\s*\.\s*(?:call|apply|bind)\s*\("),
    re.compile(r"\(\s*0\s*,\s*agent\s*\)\s*\("),
)


def _agent_call_offsets(source: str) -> list[int]:
    """Return direct non-empty ``agent(`` call offsets.

    Provider calls always pass a prompt as their first argument.  Prose/comments in
    these workflows use the empty illustrative spelling ``agent()``; excluding that
    exact shape avoids treating documentation inside long template literals as code
    while retaining every one of the banked 81 call sites.
    """
    calls: list[int] = []
    offset = 0
    in_block_comment = False
    pattern = re.compile(
        r"(?:^\s*|=>\s*|return\s+|await\s+|=\s*|:\s*)agent\s*\((?!\s*\))"
    )
    for line in source.splitlines(keepends=True):
        stripped = line.lstrip()
        if in_block_comment:
            if "*/" in line:
                in_block_comment = False
            offset += len(line)
            continue
        if stripped.startswith("/*"):
            in_block_comment = "*/" not in stripped
            offset += len(line)
            continue
        if stripped.startswith(("//", "*")):
            offset += len(line)
            continue
        calls.extend(offset + match.start() for match in pattern.finditer(line))
        offset += len(line)
    return calls


def _candidate_files(root: Path) -> set[str]:
    found: set[str] = set()
    for rel in SCAN_ROOTS:
        base = root / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix in SUFFIXES and not any(
                part in {"archive", "node_modules", ".venv"} for part in path.parts
            ):
                found.add(path.relative_to(root).as_posix())
    return found


def audit(root: Path = ROOT) -> dict[str, object]:
    violations: list[str] = []
    gated_calls = 0
    raw_calls = 0
    expected = set(WORKFLOWS)
    for rel in sorted(expected | _candidate_files(root)):
        path = root / rel
        if not path.is_file():
            if rel in expected:
                violations.append(f"MISSING:{rel}")
            continue
        source = path.read_text(encoding="utf-8")
        calls = _agent_call_offsets(source)
        if not calls:
            continue
        binding = "agent = bindDispatchAgent(agent,"
        binding_at = source.find(binding)
        if rel not in expected:
            violations.append(f"UNREGISTERED_PROVIDER_PATH:{rel}")
        if "dispatch_gate.mjs" not in source or binding_at < 0 or binding_at > calls[0]:
            violations.append(f"RAW_AGENT:{rel}:{len(calls)}")
            raw_calls += len(calls)
            continue
        for pattern in FORBIDDEN_ALIAS:
            if pattern.search(source):
                violations.append(f"PROVIDER_ALIAS:{rel}:{pattern.pattern}")
        gated_calls += len(calls)
    if gated_calls != EXPECTED_AGENT_CALLS:
        violations.append(
            f"AGENT_INVENTORY_MOVED:expected={EXPECTED_AGENT_CALLS}:observed={gated_calls}"
        )

    raptor = root / "src/atlas/tools/raptor_fold.py"
    raptor_source = raptor.read_text(encoding="utf-8") if raptor.is_file() else ""
    gate_at = raptor_source.find("_verify_dispatch_admission(prompt, label, admission)")
    claude_at = raptor_source.find('"claude", "-p"')
    run_at = raptor_source.find("proc = subprocess.run(cmd")
    if not (0 <= gate_at < claude_at < run_at):
        violations.append("RAW_RAPTOR_CLAUDE_P")
    return {
        "schema_version": "laplace.dispatch-gate-audit/1",
        "workflow_files": len(expected),
        "gated_agent_calls": gated_calls,
        "raw_agent_calls": raw_calls,
        "raptor_raw": "RAW_RAPTOR_CLAUDE_P" in violations,
        "violations": violations,
        "status": "PASS" if not violations else "REFUSED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = audit(args.root)
    print(result)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
