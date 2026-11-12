"""Conformance guard for P14: any scripts/*.py that top-level-imports laplace must carry the
src-path bootstrap (see wake.py:13-16, install_front_launcher.py:22-25) so it survives bare
`python3` on a machine with no editable install, not just `.venv/bin/python`.

The guard is deliberately STATIC.  On this machine `laplace` is editable-installed into the
system interpreter, so a cold run of any script succeeds whether or not it bootstraps -- a
behavioural probe here proves nothing about the machine the law exists to protect.

Reconstruction surfaced 7 pre-existing offenders beyond the packet's target (mech_closure.py) --
tracked in _KNOWN_LEGACY_GAPS rather than silently exempted, since they're out of this packet's
ownership scope.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"

# Pre-existing scripts that top-level-import laplace without the bootstrap (found by this
# test, 2026-07-12), not fixed here because they're outside P14's ownership. Shrink this set
# as each gets its own bootstrap fix.
_KNOWN_LEGACY_GAPS = frozenset({
    "assign_orphans.py",
    "fire_test.py",
    "fire_test_ops.py",
    "mech_closure_lens.py",
    "pour_conceptric.py",
    "project_residue.py",
    "router_reach_audit.py",
})


def _is_laplace_import(node: ast.stmt) -> bool:
    if isinstance(node, ast.Import):
        return any(a.name == "laplace" or a.name.startswith("laplace.") for a in node.names)
    if isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        return node.level == 0 and (mod == "laplace" or mod.startswith("laplace."))
    return False


def _is_sys_path_mutation(node: ast.stmt) -> bool:
    """Any shape that writes to sys.path: insert/append/extend calls, `sys.path[:0] = [...]`,
    `sys.path += [...]`, or a whole-name rebind.  The law is that sys.path is arranged before
    laplace is imported -- not which of the five idioms in this tree spells it."""
    def _is_sys_path(expr: ast.expr) -> bool:
        return (
            isinstance(expr, ast.Attribute)
            and expr.attr == "path"
            and isinstance(expr.value, ast.Name)
            and expr.value.id == "sys"
        )

    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        func = node.value.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr in {"insert", "append", "extend"}
            and _is_sys_path(func.value)
        )
    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        targets = [node.target]
    for tgt in targets:
        if _is_sys_path(tgt):
            return True
        if isinstance(tgt, ast.Subscript) and _is_sys_path(tgt.value):
            return True
    return False


def _import_error_guarded(node: ast.stmt) -> bool:
    """A `try: from laplace import x / except ImportError: ...` site.  Either the handler
    bootstraps and retries (build_design_conceptric.py:56-60) or the script degrades to a
    laplace-free path (ensure_state.py:42-46).  Both survive bare `python3`, so a guarded
    import is not what the law is about -- the unguarded one is."""
    if not isinstance(node, ast.Try):
        return False
    for handler in node.handlers:
        names = handler.type
        if names is None:
            return True
        for expr in (names.elts if isinstance(names, ast.Tuple) else [names]):
            if isinstance(expr, ast.Name) and expr.id in {"ImportError", "ModuleNotFoundError", "Exception"}:
                return True
    return False


def _names_src(node: ast.stmt) -> bool:
    text = ast.unparse(node)
    return "'src'" in text or '"src"' in text


def _has_bootstrap(src: str) -> bool:
    """True unless some UNGUARDED top-level laplace import runs with no preceding sys.path
    mutation naming a `src` path component.  Ordering is part of the law: a bootstrap that
    lands after the import it is meant to enable is not a bootstrap.  Idiom is not part of
    the law: five spellings live in this tree (`sys.path.insert`, `sys.path[:0] = [...]`,
    an `os.path.join` argument, a named `SRC` variable, an `if ... not in sys.path` guard)
    and the AST sees all of them."""
    bootstrapped = False
    saw_src = False

    def walk(body: list[ast.stmt]) -> bool:
        nonlocal bootstrapped, saw_src
        for node in body:
            # the `src` path component may be named on the mutation itself
            # (wake.py:15) or bound to a variable just above it
            # (install_front_launcher.py:23-25); either counts.
            if _names_src(node):
                saw_src = True
            if _is_sys_path_mutation(node) and saw_src:
                bootstrapped = True
                continue
            if _is_laplace_import(node):
                if not bootstrapped:
                    return False
                continue
            if isinstance(node, ast.If):
                if not walk(node.body) or not walk(node.orelse):
                    return False
            elif isinstance(node, ast.Try):
                if _import_error_guarded(node):
                    # opaque as an import site, but its handler may still bootstrap
                    for handler in node.handlers:
                        for inner in handler.body:
                            if _names_src(inner):
                                saw_src = True
                            if _is_sys_path_mutation(inner) and saw_src:
                                bootstrapped = True
                    continue
                for part in (node.body, node.orelse, node.finalbody):
                    if not walk(part):
                        return False
                for handler in node.handlers:
                    if not walk(handler.body):
                        return False
        return True

    return walk(ast.parse(src).body)


def _module_level(body: list[ast.stmt]):
    """Module-level statements, descending into `if`/`try` but never into functions or
    classes -- an import inside a function is not the top-level dependency this guards."""
    for node in body:
        yield node
        if isinstance(node, ast.If):
            yield from _module_level(node.body)
            yield from _module_level(node.orelse)
        elif isinstance(node, ast.Try):
            yield from _module_level(node.body)
            for handler in node.handlers:
                yield from _module_level(handler.body)
            yield from _module_level(node.orelse)
            yield from _module_level(node.finalbody)


def _laplace_importing_scripts():
    for path in sorted(SCRIPTS_DIR.glob("*.py")):
        if "_archive" in path.parts:
            continue
        src = path.read_text(encoding="utf-8")
        if any(_is_laplace_import(node) for node in _module_level(ast.parse(src).body)):
            yield path, src


def test_mech_closure_has_bootstrap():
    """The P14 fix itself: mech_closure.py must now carry the src-path bootstrap."""
    src = (SCRIPTS_DIR / "mech_closure.py").read_text(encoding="utf-8")
    assert _has_bootstrap(src), "mech_closure.py is missing the src-path bootstrap"
    assert "mech_closure.py" not in _KNOWN_LEGACY_GAPS


def test_laplace_importing_scripts_carry_bootstrap():
    """Whole-class guard: every scripts/*.py that top-level-imports laplace must bootstrap
    sys.path, except the tracked legacy gaps."""
    offenders = [
        path.name
        for path, src in _laplace_importing_scripts()
        if path.name not in _KNOWN_LEGACY_GAPS and not _has_bootstrap(src)
    ]
    assert not offenders, f"scripts missing src-path bootstrap: {offenders}"


def test_known_legacy_gaps_stay_accurate():
    """Catches drift: once a tracked file is fixed elsewhere, it must be dropped from the set."""
    fixed = [
        path.name
        for path, src in _laplace_importing_scripts()
        if path.name in _KNOWN_LEGACY_GAPS and _has_bootstrap(src)
    ]
    assert not fixed, f"remove from _KNOWN_LEGACY_GAPS, now compliant: {fixed}"
