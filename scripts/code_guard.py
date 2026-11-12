#!/usr/bin/env python3
"""Write-time guard for the Atlas system package: slow code is refused BEFORE it lands.

The author, 2026-09-22: "BUT IT SHOULDN'T BE DOWN TO THE JUDGE. THE DAMAGE IS ALREADY DONE WHEN
THE BUILDER DOES IT". Measured the same night: an ingestion path that was 97% overhead (a quadratic
Python loop over one collection, 21,035 separate torch.tensor() calls, a process pool created per
call) had been written, run for hours and accepted, because every efficiency check sat after the
builder. This runs as a PreToolUse hook on Write and Edit: it parses what the file WOULD become and
refuses the write when it ADDS one of the measured patterns. The refusal text names the line and
the rewrite, so the builder fixes it in the same turn. Stdlib only; a few milliseconds per write.

Rules (each refuses only violations the edit ADDS; what a legacy file already contains is not
blamed on an unrelated edit):
  TENSOR-PER-ELEMENT  torch.tensor / as_tensor / arange / zeros / empty / full, or .item() /
                      .tolist() / .cpu() / .numpy(), inside a loop or comprehension.
  TENSOR-UNPACKED     a `for` that iterates a tensor unpacked on the host (.tolist(), .numpy(),
                      range(x.numel()), range(x.shape[0])).
  ALL-PAIRS           a loop or comprehension over a collection nested inside a loop over the SAME
                      collection - a quadratic pass that a hash, a sort or a join replaces.
  POOL-PER-CALL       a process pool, executor, Process or subprocess created anywhere without
                      the annotation `# pool-once: <who calls this once per run>`.
  SLEEP               time.sleep in the system package.
  DENSE-PAIRS         torch.zeros/empty/full/ones sized by a product of two counts or by one count twice
                      (found 2026-09-22: an F x F int64 matrix, 800 MB at F = 10,000, OOM at 20,000).
A loop that is genuinely over a small closed set (lenses, relation kinds, columns, levels) carries
`# loop-ok: <what bounds it>` on its `for` line; the annotation is visible to every judge.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from collections import Counter

GUARDED = (os.sep + os.path.join("atlas", "src", "atlas") + os.sep,)
TENSOR_MAKERS = {"tensor", "as_tensor", "arange", "zeros", "empty", "full", "ones"}
HOST_UNPACK = {"item", "tolist", "cpu", "numpy"}
POOLS = {"Pool", "ProcessPoolExecutor", "ThreadPoolExecutor", "Process", "Popen"}
FIX = {
    "TENSOR-PER-ELEMENT": "collect values in a list or NumPy array and make ONE tensor per column per batch, after the loop",
    "TENSOR-UNPACKED": "keep the work on the device as a whole-array operation (mask, gather, scatter, sort, unique, bucketize); unpack once at the very end if the host needs the result",
    "ALL-PAIRS": "this is quadratic in the collection: index one side in a dict or sorted array (hash the key, e.g. token n-grams) and look the other side up - linear or n log n",
    "POOL-PER-CALL": "create the pool ONCE per run in the entry that owns it, reuse it, make the worker module import nothing heavy (no torch), and mark the line `# pool-once: <who calls this once per run>`",
    "SLEEP": "nothing in the system waits on a clock; wait on the thing itself",
    "DENSE-PAIRS": "an allocation sized by the PRODUCT of two counts (n*n, F*F, or the same count twice) is a dense all-pairs object: build the sparse (i, j, value) triple instead - pack (i*n + j) into one int64 key, sort, unique_consecutive - or, if it is a small fixed block, say what bounds it with `# dense-ok: <bound>`",
}


def _name(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover
        return ""


class _Lint(ast.NodeVisitor):
    def __init__(self, lines):
        self.lines, self.out, self.loops = lines, [], []   # loops: stack of (iter_source, lineno)

    def _ok(self, lineno, tag):
        line = self.lines[lineno - 1] if 0 < lineno <= len(self.lines) else ""
        return tag in line

    def _flag(self, rule, node):
        line = self.lines[node.lineno - 1].strip() if 0 < node.lineno <= len(self.lines) else ""
        self.out.append((rule, node.lineno, line))

    def _enter_loop(self, iter_node, lineno, body_nodes):
        src = _name(iter_node)
        annotated = self._ok(lineno, "# loop-ok:")
        if not annotated:
            if any(f".{m}(" in src for m in ("tolist", "numpy")) or ".numel()" in src or ".shape[0]" in src:
                self.out.append(("TENSOR-UNPACKED", lineno, self.lines[lineno - 1].strip()))
            base = src.split("[")[0].strip()
            for outer_src, _ in self.loops:
                if base and base == outer_src.split("[")[0].strip() and base.isidentifier():
                    self.out.append(("ALL-PAIRS", lineno, self.lines[lineno - 1].strip()))
                    break
        self.loops.append((src, lineno) if not annotated else ("", lineno))
        for n in body_nodes:
            self.visit(n)
        self.loops.pop()

    def visit_For(self, node):
        self.visit(node.iter)
        self._enter_loop(node.iter, node.lineno, node.body + node.orelse)

    visit_AsyncFor = visit_For

    def visit_While(self, node):
        self.loops.append(("", node.lineno))
        self.generic_visit(node)
        self.loops.pop()

    def _comp(self, node, elts):
        gens = node.generators
        def rec(i):
            if i == len(gens):
                for e in elts:
                    self.visit(e)
                return
            self.visit(gens[i].iter) if i == 0 else None
            self._enter_loop_comp(gens[i], lambda: rec(i + 1))
        rec(0)

    def _enter_loop_comp(self, gen, inner):
        src = _name(gen.iter)
        lineno = getattr(gen.iter, "lineno", 0)
        base = src.split("[")[0].strip()
        if not self._ok(lineno, "# loop-ok:"):
            if any(f".{m}(" in src for m in ("tolist", "numpy")):
                self.out.append(("TENSOR-UNPACKED", lineno, self.lines[lineno - 1].strip()))
            for outer_src, _ in self.loops:
                if base and base == outer_src.split("[")[0].strip() and base.isidentifier():
                    self.out.append(("ALL-PAIRS", lineno, self.lines[lineno - 1].strip()))
                    break
        self.loops.append((src, lineno))
        for cond in gen.ifs:
            self.visit(cond)
        inner()
        self.loops.pop()

    def visit_ListComp(self, node):
        self._comp(node, [node.elt])

    visit_SetComp = visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, node):
        self._comp(node, [node.key, node.value])

    def visit_Call(self, node):
        f = node.func
        attr = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
        owner = _name(f.value) if isinstance(f, ast.Attribute) else ""
        in_loop = any(src != "" or True for src, _ in self.loops) and bool(self.loops)
        loop_ok = bool(self.loops) and all(self._ok(ln, "# loop-ok:") for _, ln in self.loops)
        if in_loop and not loop_ok:
            if (attr in TENSOR_MAKERS and owner in ("torch", "np", "numpy")) or (attr in HOST_UNPACK and isinstance(f, ast.Attribute) and not node.args):
                self._flag("TENSOR-PER-ELEMENT", node)
        if attr in POOLS or (owner == "subprocess" and attr in ("run", "call", "check_output")) or (owner == "os" and attr == "system"):
            if not self._ok(node.lineno, "# pool-once:"):
                self._flag("POOL-PER-CALL", node)
        if owner == "time" and attr == "sleep":
            self._flag("SLEEP", node)
        if attr in ("zeros", "empty", "full", "ones") and owner in ("torch", "np", "numpy") and node.args:
            shape = node.args[0]
            def _is_product(e):
                return isinstance(e, ast.BinOp) and isinstance(e.op, (ast.Mult, ast.Pow))
            dims = list(shape.elts) if isinstance(shape, (ast.Tuple, ast.List)) else [shape]
            names = [_name(d).split("[")[0].split(".")[0] for d in dims]
            if any(_is_product(d) for d in dims) or (len(names) >= 2 and len(set(n for n in names if n and n.isidentifier())) < len([n for n in names if n and n.isidentifier()])):
                if not self._ok(node.lineno, "# dense-ok:"):
                    self._flag("DENSE-PAIRS", node)
        self.generic_visit(node)


def lint(text: str):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []                      # a syntax error is the interpreter's job to report
    v = _Lint(text.splitlines())
    v.visit(tree)
    return v.out


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--check":
        # the same rules over whole files: what a builder runs before it reports, and the backstop for a
        # file written by a shell command, which the write hook does not see
        bad = 0
        for path in sys.argv[2:]:
            try:
                found = lint(open(path, encoding="utf-8").read())
            except OSError:
                continue
            for rule, lineno, line in found:
                bad += 1
                print(f"{path}:{lineno}: {rule}: {line[:120]}\n    -> {FIX[rule]}")
        print(f"code_guard: {bad} slow-code pattern(s)")
        return 1 if bad else 0
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    tool, inp = event.get("tool_name") or "", event.get("tool_input") or {}
    path = os.path.abspath(str(inp.get("file_path") or ""))
    if not path.endswith(".py") or not any(g in path for g in GUARDED):
        return 0
    try:
        before = open(path, encoding="utf-8").read()
    except OSError:
        before = ""
    if tool == "Write":
        after = str(inp.get("content") or "")
    elif tool == "Edit":
        old, new = str(inp.get("old_string") or ""), str(inp.get("new_string") or "")
        if old not in before:
            return 0                    # the edit will fail on its own terms
        after = before.replace(old, new) if inp.get("replace_all") else before.replace(old, new, 1)
    else:
        return 0
    had = Counter((r, l) for r, _, l in lint(before))
    added = []
    for rule, lineno, line in lint(after):
        if had[(rule, line)] > 0:
            had[(rule, line)] -= 1
            continue
        added.append((rule, lineno, line))
    if not added:
        return 0
    msg = [f"WRITE REFUSED by scripts/code_guard.py - this edit adds {len(added)} slow-code pattern(s) to {os.path.relpath(path)}. "
           "Rewrite and write again; slow code is refused before it lands, not found by a judge afterwards."]
    for rule, lineno, line in added[:12]:
        msg.append(f"  {rule} at line {lineno}: {line[:140]}\n      -> {FIX[rule]}")
    msg.append("A loop over a genuinely small closed set (lenses, relation kinds, columns, levels) carries `# loop-ok: <what bounds it>` on its for-line.")
    print("\n".join(msg), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
