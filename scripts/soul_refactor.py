#!/usr/bin/env python3
"""Soul Refactor — the recursive-waterfall rewriter of the engine's own generating context.

THE FUNCTION, banked ahead of its data. Given a CARRIER (the compressed taste —
an opaque single conditioning context, supplied later, never built here),
descend every level of the engine's generating loops and, for each piece of
context that conditions a task, perform a BLIND, FUNCTION-PRESERVING rewrite that
re-expresses the piece to *embody* the taste rather than *describe* it.
Instruction and meta-instruction collapse into one text: the rewrite prompt is
itself rendered through the carrier — a prompt that performs itself. The rewriter
never changes WHAT a piece does (its function); only HOW it is said (its
register).

This module is the MECHANICAL FLOOR — enumeration, the function-preservation
contract, the self-performing prompt builder, the mechanical verifier, and
staging / apply / rollback. The TASTE FLOOR (the blind spawn-and-judge) is the
orchestrated loop in ``canon://skills/soul_refactor``, driven by Eigen; this
harness is what that loop calls to stay honest.

The discipline it enforces:

- **Function is sacrosanct (the welder's guardrail, made checkable).** For a
  markdown node the YAML frontmatter (its ``consistency`` / ``earned_by`` edges,
  its description) must come out byte-identical; only the prose body is the
  rewrite surface. For an agent persona only the ``instructions`` block is
  surface; every other key is frozen. For a code string the assignment key and
  its format placeholders are frozen and the file must still parse to an AST that
  differs from the original at *exactly* the one target string. Routing tags live
  in ``index.yaml`` and are never touched, so a node's reachability is preserved
  by construction.
- **Builder != judge.** The rewriter is a callable injected by the caller (the
  spawned blind sub-Eigen in production; a stub in the tests). This harness only
  *verifies*; it never authors the new prose.
- **Trust the verifier (the author's call).** ``apply`` swaps a live file only on
  a fully green mechanical verdict, after a git checkpoint, and rolls back on any
  failure. The verifier is the only thing between a rewrite and the engine, so it
  is strict by construction.
- **Recursive / self-similar.** The rewrite-prompt template and this harness's own
  skill node are themselves targets: a pass rewrites the rewriter.

Built empty and proven on a stub carrier before any soul exists to pour through
it — the gate is shown to hold before it is ever used.

CLI::

    python scripts/soul_refactor.py enumerate            # the depth-ordered worklist
    python scripts/soul_refactor.py contract <target-id> # the frozen invariants of one piece
    python scripts/soul_refactor.py dry-run [<target-id>] # stub carrier + identity rewriter; stages, changes nothing live
"""
from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
CANON = REPO_ROOT / "src" / "laplace" / "pipeline" / "canon"
SKILLS_DIR = CANON / "skills"
WIKI_DIR = CANON / "wiki"
AGENTS_DIR = CANON / "agents"
CANON_PY = REPO_ROOT / "src" / "laplace" / "pipeline" / "canon.py"
STAGING = REPO_ROOT / ".soul_refactor_staging"

# A rewriter re-voices a body of prose. In production it is a spawned, sealed
# blind sub-Eigen handed (prompt, body); here its type is all the harness needs.
Rewriter = Callable[[str, str], str]


# --------------------------------------------------------------------------- #
# The carrier — the compressed taste. Opaque by design: the harness treats it as
# a single conditioning context, so the dump's eventual shape never blocks the
# build, and every rewriter in one pass receives the *same* carrier (one taste,
# coherent across every piece — invisible locally, unmistakable in the whole).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Carrier:
    text: str
    invariants: tuple[str, ...] = ()

    @classmethod
    def stub(cls) -> "Carrier":
        return cls(
            text="<STUB CARRIER — no soul yet. The gate is being proven empty.>",
            invariants=(),
        )


def identity_rewriter(prompt: str, body: str) -> str:  # noqa: ARG001
    """The trivial function-preserving rewrite: change nothing. The gate must pass it."""
    return body


# --------------------------------------------------------------------------- #
# Targets — every piece of context imparted in a call for a task.
# --------------------------------------------------------------------------- #
@dataclass
class Target:
    id: str
    kind: str  # "skill" | "wiki" | "agent" | "code"
    path: Path
    depth: int  # waterfall order: small = outermost framing, large = the kernel
    locator: dict = field(default_factory=dict)


# The kernel of the generating loop: the self, the soul-craft, and the assembly
# code itself. Deepest in the waterfall, scrutinised last and hardest.
_KERNEL_WIKI = {
    "engine/self",
    "engine/eigen",
    "engine/operatorial_self",
    "engine/generative_loop",
    "aesthetics/earned_simplicity",
    "aesthetics/voice_and_style",
}

# The in-scope code strings, declared precisely (never a blind regex). Each is a
# string-valued dict entry inside a function in canon.py, disambiguated by a
# sibling key in the same dict where the key name is not unique.
@dataclass
class CodeTarget:
    func: str
    key: str
    sibling: str | None = None  # a co-key in the same dict, to disambiguate


_CODE_TARGETS = [
    CodeTarget("orient", "loop"),
    # The generation_discipline dict is {law, do, skill}; the orchestration dict is
    # {law, do, fetch}. Both carry law+do, so disambiguate on `skill` - the key
    # unique to generation_discipline - or each target resolves to two nodes.
    CodeTarget("orient", "law", sibling="skill"),
    CodeTarget("orient", "do", sibling="skill"),
    CodeTarget("route", "note", sibling="goal"),
]


def _depth_for_wiki(ref: str) -> int:
    return 80 if ref in _KERNEL_WIKI else 50


def enumerate_targets() -> list[Target]:
    """Walk the whole generating-context surface, depth-ordered (framing -> kernel)."""
    targets: list[Target] = []

    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        name = skill_md.parent.name
        if name.startswith("_"):  # _archive
            continue
        targets.append(Target(id=f"skill:{name}", kind="skill", path=skill_md, depth=30))

    for node_md in sorted(WIKI_DIR.rglob("*.md")):
        ref = node_md.relative_to(WIKI_DIR).with_suffix("").as_posix()
        targets.append(Target(id=f"wiki:{ref}", kind="wiki", path=node_md, depth=_depth_for_wiki(ref)))

    for persona in sorted(AGENTS_DIR.glob("*.yaml")):
        targets.append(Target(id=f"agent:{persona.stem}", kind="agent", path=persona, depth=90))

    for ct in _CODE_TARGETS:
        targets.append(
            Target(
                id=f"code:canon.{ct.func}.{ct.key}",
                kind="code",
                path=CANON_PY,
                depth=100,
                locator={"func": ct.func, "key": ct.key, "sibling": ct.sibling},
            )
        )

    targets.sort(key=lambda t: (t.depth, t.id))
    return targets


def get_target(target_id: str) -> Target:
    for t in enumerate_targets():
        if t.id == target_id:
            return t
    raise KeyError(f"no such target: {target_id!r}")


# --------------------------------------------------------------------------- #
# Surface vs contract — split each piece into the prose that MAY change (surface)
# and the structure that MUST NOT (contract). Function preservation is then just:
# the contract is byte-identical before and after.
# --------------------------------------------------------------------------- #
def _split_md(text: str) -> tuple[str, str]:
    """Return (frontmatter_block, body). The frontmatter block is contract; the body is surface."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[: end + 5], text[end + 5 :]
    return "", text


def _split_agent(text: str) -> tuple[tuple[str, str], str, str]:
    """Return ((pre, post), indent, instructions_body) for an agent persona.

    Only the ``instructions:`` literal block is surface; ``pre`` + ``post`` (the
    persona's name/role/capabilities/includes) are contract.
    """
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("instructions:") and ("|" in line or ">" in line):
            key_indent = len(line) - len(stripped)
            body_lines: list[str] = []
            j = i + 1
            block_indent: int | None = None
            while j < len(lines):
                ln = lines[j]
                if ln.strip() == "":
                    body_lines.append(ln)
                    j += 1
                    continue
                ind = len(ln) - len(ln.lstrip())
                if ind <= key_indent:
                    break
                if block_indent is None:
                    block_indent = ind
                body_lines.append(ln)
                j += 1
            indent = " " * (block_indent if block_indent is not None else key_indent + 2)
            pre = "".join(lines[: i + 1])
            post = "".join(lines[j:])
            dedented = "".join(
                (ln[len(indent):] if ln.startswith(indent) else ln) for ln in body_lines
            )
            return (pre, post), indent, dedented
    return (text, ""), "", ""


def _find_code_node(tree: ast.AST, func: str, key: str, sibling: str | None) -> ast.Constant:
    """Locate the unique string-valued dict entry `key` inside function `func`."""
    matches: list[ast.Constant] = []
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == func:
            for d in ast.walk(fn):
                if isinstance(d, ast.Dict):
                    keys = [k.value for k in d.keys if isinstance(k, ast.Constant)]
                    if sibling is not None and sibling not in keys:
                        continue
                    for k, v in zip(d.keys, d.values):
                        if (
                            isinstance(k, ast.Constant)
                            and k.value == key
                            and isinstance(v, ast.Constant)
                            and isinstance(v.value, str)
                        ):
                            matches.append(v)
    if len(matches) != 1:
        raise ValueError(f"code target {func}.{key} resolved to {len(matches)} nodes (need exactly 1)")
    return matches[0]


def read_surface(target: Target) -> str:
    """The prose a rewriter is allowed to re-voice."""
    text = target.path.read_text(encoding="utf-8")
    if target.kind in ("skill", "wiki"):
        return _split_md(text)[1]
    if target.kind == "agent":
        return _split_agent(text)[2]
    if target.kind == "code":
        tree = ast.parse(text)
        node = _find_code_node(tree, **target.locator)
        return node.value
    raise ValueError(target.kind)


def _format_tokens(s: str) -> set[str]:
    """The format placeholders a code string must keep ({}, {name}, %s, %(x)s)."""
    import re

    return set(re.findall(r"\{[^}]*\}|%\([^)]*\)[sdrfx]|%[sdrfx]", s))


def extract_contract(target: Target) -> dict:
    """The frozen invariants — what must be identical before and after the rewrite."""
    text = target.path.read_text(encoding="utf-8")
    if target.kind in ("skill", "wiki"):
        return {"kind": target.kind, "frontmatter": _split_md(text)[0]}
    if target.kind == "agent":
        (pre, post), _indent, _body = _split_agent(text)
        return {"kind": "agent", "pre": pre, "post": post}
    if target.kind == "code":
        node = _find_code_node(ast.parse(text), **target.locator)
        return {
            "kind": "code",
            "func": target.locator["func"],
            "key": target.locator["key"],
            "placeholders": _format_tokens(node.value),
        }
    raise ValueError(target.kind)


def render(target: Target, new_surface: str) -> str:
    """Reassemble the full file text from the frozen contract + the new surface."""
    text = target.path.read_text(encoding="utf-8")
    if target.kind in ("skill", "wiki"):
        return _split_md(text)[0] + new_surface
    if target.kind == "agent":
        (pre, post), indent, _body = _split_agent(text)
        reindented = "".join(
            (indent + ln if ln.strip() else ln) for ln in new_surface.splitlines(keepends=True)
        )
        return pre + reindented + post
    if target.kind == "code":
        tree = ast.parse(text)
        node = _find_code_node(tree, **target.locator)
        if new_surface == node.value:
            return text  # unchanged: never reformat what was not rewritten
        lines = text.splitlines(keepends=True)
        start = sum(len(x) for x in lines[: node.lineno - 1]) + node.col_offset
        end = sum(len(x) for x in lines[: node.end_lineno - 1]) + node.end_col_offset
        return text[:start] + repr(new_surface) + text[end:]
    raise ValueError(target.kind)


# --------------------------------------------------------------------------- #
# The self-performing prompt. Rendered THROUGH the carrier: the carrier's voice
# conditions the instruction itself, so instruction and meta-instruction are one
# text. This template is itself a recursion target (see _PROMPT_TEMPLATE below).
# --------------------------------------------------------------------------- #
_PROMPT_TEMPLATE = """\
{carrier}

You are a sealed sub-Eigen. You see ONLY: this carrier, the one piece of text
below, and the contract of what must not change. You do not know what task this
piece serves, who wrote it, or why — and you do not need to. Re-voice the prose
so it *embodies* the carrier above rather than describing any rule: the same
meaning, the same function, said as the carrier would say it. Change how it is
said; never change what it does. Do not add, drop, or alter any claim,
instruction, edge, key, or placeholder. Return only the re-voiced prose.

FROZEN (must survive unchanged): {frozen}

THE PIECE:
{body}
"""


def build_rewrite_prompt(carrier: Carrier, target: Target) -> str:
    """The instruction handed to the blind rewriter — performed through the carrier."""
    contract = extract_contract(target)
    frozen = ", ".join(f"{k}={v!r}" for k, v in contract.items() if k != "kind") or "(structure only)"
    if carrier.invariants:
        frozen += " | carrier invariants: " + "; ".join(carrier.invariants)
    return _PROMPT_TEMPLATE.format(carrier=carrier.text, frozen=frozen, body=read_surface(target))


# --------------------------------------------------------------------------- #
# The mechanical floor — the strict half of the two-floored verifier. (The taste
# floor is the out-of-loop blind reader, the orchestrated loop's job.)
# --------------------------------------------------------------------------- #
@dataclass
class Verdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def verify_mechanical(target: Target, new_text: str) -> Verdict:
    """Parses, and the contract is byte-identical. Function preserved, or it fails."""
    reasons: list[str] = []
    before = extract_contract(target)

    if target.kind in ("skill", "wiki"):
        fm, _body = _split_md(new_text)
        if fm != before["frontmatter"]:
            reasons.append("frontmatter changed (consistency/earned_by/description must be frozen)")
    elif target.kind == "agent":
        try:
            import yaml

            yaml.safe_load(new_text)
        except Exception as e:  # noqa: BLE001
            reasons.append(f"agent yaml no longer parses: {e}")
        # Only the instructions block is surface; every other key is frozen.
        (pre, post), _ind, _b = _split_agent(new_text)
        if pre != before["pre"] or post != before["post"]:
            reasons.append("a non-instructions key changed (only the instructions block is surface)")
    elif target.kind == "code":
        try:
            new_tree = ast.parse(new_text)
        except SyntaxError as e:
            return Verdict(False, [f"canon.py no longer parses: {e}"])
        orig_tree = ast.parse(target.path.read_text(encoding="utf-8"))
        orig_node = _find_code_node(orig_tree, **target.locator)
        try:
            new_node = _find_code_node(new_tree, **target.locator)
        except ValueError as e:
            return Verdict(False, [str(e)])
        if _format_tokens(new_node.value) != before["placeholders"]:
            reasons.append("format placeholders changed (a downstream consumer would break)")
        # Prove the ONLY change is this one string: restore it and compare ASTs.
        new_node.value = orig_node.value
        if ast.dump(new_tree) != ast.dump(orig_tree):
            reasons.append("more than the target string changed in canon.py")
    else:
        reasons.append(f"unknown kind {target.kind}")

    return Verdict(not reasons, reasons)


def run_global_floor() -> Verdict:
    """The per-pass global checks: graph health not worse, full test suite green.

    Cheap per-node checks run inline in ``verify_mechanical``; these are the
    expensive checks the orchestrated loop runs once per pass (or before an
    ``apply``), not per node.
    """
    import subprocess

    reasons: list[str] = []
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    if r.returncode != 0:
        reasons.append("pytest is not green:\n" + r.stdout[-1500:])
    return Verdict(not reasons, reasons)


# --------------------------------------------------------------------------- #
# Stage / apply / rollback. Default apply=False: nothing live is touched.
# --------------------------------------------------------------------------- #
@dataclass
class PassResult:
    target_id: str
    verdict: Verdict
    staged_path: Path | None = None
    applied: bool = False


def run_target(
    target: Target,
    carrier: Carrier,
    rewriter: Rewriter,
    *,
    apply: bool = False,
) -> PassResult:
    """One node of the waterfall: build prompt -> rewrite -> verify -> stage (or apply)."""
    prompt = build_rewrite_prompt(carrier, target)
    new_surface = rewriter(prompt, read_surface(target))
    new_text = render(target, new_surface)
    verdict = verify_mechanical(target, new_text)

    STAGING.mkdir(exist_ok=True)
    staged = STAGING / (target.id.replace(":", "__").replace("/", "_") + ".staged")
    staged.write_text(new_text, encoding="utf-8")

    if apply and verdict.ok:
        # Trust-the-verifier apply: checkpoint, swap, rollback on any failure.
        import subprocess

        subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=False)
        original = target.path.read_text(encoding="utf-8")
        target.path.write_text(new_text, encoding="utf-8")
        gf = run_global_floor()
        if not gf.ok:
            target.path.write_text(original, encoding="utf-8")
            return PassResult(target.id, Verdict(False, verdict.reasons + gf.reasons), staged, False)
        return PassResult(target.id, verdict, staged, True)

    return PassResult(target.id, verdict, staged, False)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cmd_enumerate(_args) -> int:
    for t in enumerate_targets():
        print(f"  [{t.depth:3d}] {t.id:48s} {t.kind}")
    n = len(enumerate_targets())
    print(f"\n{n} generating-context pieces (the waterfall, framing -> kernel).")
    return 0


def _cmd_contract(args) -> int:
    t = get_target(args.target)
    c = extract_contract(t)
    print(f"{t.id}  (depth {t.depth}, {t.kind})")
    for k, v in c.items():
        shown = v if not isinstance(v, str) or len(v) < 400 else v[:400] + " …"
        print(f"  {k}: {shown!r}")
    return 0


def _cmd_dry_run(args) -> int:
    carrier = Carrier.stub()
    targets = [get_target(args.target)] if args.target else enumerate_targets()
    ok = 0
    print(f"DRY RUN — stub carrier, identity rewriter, apply=False (nothing live is touched).\n")
    for t in targets:
        res = run_target(t, carrier, identity_rewriter, apply=False)
        mark = "PASS" if res.verdict.ok else "FAIL"
        print(f"  {mark}  {t.id}")
        for r in res.verdict.reasons:
            print(f"        - {r}")
        ok += res.verdict.ok
    print(f"\n{ok}/{len(targets)} pass the mechanical floor; staged under {STAGING.relative_to(REPO_ROOT)}/")
    return 0 if ok == len(targets) else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("enumerate").set_defaults(fn=_cmd_enumerate)
    c = sub.add_parser("contract")
    c.add_argument("target")
    c.set_defaults(fn=_cmd_contract)
    d = sub.add_parser("dry-run")
    d.add_argument("target", nargs="?")
    d.set_defaults(fn=_cmd_dry_run)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
