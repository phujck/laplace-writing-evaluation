"""Compute source-backed cards without importing actuators or opening an Atlas store."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import re
import shlex
from functools import lru_cache
from pathlib import Path

from .errors import StoreError

PACKAGE = Path(__file__).resolve().parent
CONTAINER = PACKAGE.parents[1] / "atlas"   # src/atlas since core consolidation R2: the container is <checkout>/atlas
ROOT = CONTAINER.parent if (CONTAINER.parent / "src/laplace").is_dir() else CONTAINER
CACHE_SCHEMA = "atlas.cards-registry-cache/1"
SOURCE_RECEIPT_SCHEMA = "atlas.cards-source-receipt/1"


def _rel(path: Path) -> str:
    """A path relative to the container's root when it lies under it, else as given: a card
    computed over a package staged outside the tree (tests) still names its source."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


@lru_cache(maxsize=256)
def _parse(path: str, mtime: int, size: int) -> ast.Module:
    return ast.parse(Path(path).read_text(encoding="utf-8"), filename=path)


def _tree(path: Path) -> ast.Module:
    stat = path.stat()
    return _parse(str(path), stat.st_mtime_ns, stat.st_size)


def _files(root: Path):
    # Enumerate package source only, never store directories. Also works in the
    # cold-descent test where Path.glob/iterdir are deliberately forbidden.
    # Scratch trees are never package source: an executor's in-repo pytest basetemp under
    # atlas/tests/ nested into itself through the relocation test until the path exceeded the OS
    # limit and this walk raised (2026-09-14). Skip pytest-* and dot directories; never raise on
    # an unreadable directory - a card registry that cannot be computed is a page that refuses.
    for directory, dirs, files in os.walk(root, onerror=lambda _exc: None):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__" and not d.startswith(".")
                         and not d.startswith("pytest-") and not d.startswith("tmp"))
        for name in sorted(files):
            if name.endswith(".py"):
                yield Path(directory) / name


def _cache_root(package: Path, tests: Path) -> Path:
    """Keep fixture caches beside their fixture and the live cache under atlas/.cache/."""
    common = Path(os.path.commonpath((package.resolve(), tests.resolve())))
    if common == Path(common.anchor):
        # a fixture staged outside the tree shares only the filesystem root with the package: its cache stays
        # beside the fixture (the docstring's rule), never at "/.cache"
        common = tests.resolve()
    return common / ".cache" / "cards"


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_json(path: Path, value: dict) -> None:
    """Atomically bank canonical JSON, without rewriting an unchanged receipt."""
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode()
    try:
        if path.read_bytes() == data:
            return
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _sha256_file(path: Path) -> tuple[os.stat_result, str]:
    """Hash stable bytes and return the stat tuple that names those bytes for the fast path."""
    for _ in range(3):
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns):
            return after, "sha256:" + digest.hexdigest()
    raise StoreError("card source changed while hashing", code="CARD-SOURCE-UNSTABLE",
                     path=str(path))


def _source_identity(package: Path, tests: Path) -> tuple[str, Path, list[dict]]:
    """Digest relative paths and blob hashes, re-hashing only stat-changed files."""
    cache_root = _cache_root(package, tests)
    receipt_path = cache_root / "sources.json"
    previous = _read_json(receipt_path)
    previous_files = previous.get("files", {}) if (
        previous and previous.get("schema_version") == SOURCE_RECEIPT_SCHEMA
        and isinstance(previous.get("files"), dict)) else {}
    # relative source names are taken from the common root of the package and the tests, which is the cache's home
    # except for a fixture staged outside the tree (then the cache sits beside the fixture and names stay anchored)
    scope_root = Path(os.path.commonpath((package.resolve(), tests.resolve())))
    files: dict[str, dict] = {}
    sources: list[dict] = []
    paths = sorted({p.resolve() for root in (package, tests) for p in _files(root)})
    for path in paths:
        relative = path.relative_to(scope_root).as_posix()
        stat = path.stat()
        prior = previous_files.get(relative, {})
        if (prior.get("size") == stat.st_size
                and prior.get("mtime_ns") == stat.st_mtime_ns
                and isinstance(prior.get("sha256"), str)):
            blob = prior["sha256"]
        else:
            stat, blob = _sha256_file(path)
        files[relative] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                           "sha256": blob}
        sources.append({"path": relative, "sha256": blob})
    identity_bytes = json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()
    content_digest = "sha256:" + hashlib.sha256(identity_bytes).hexdigest()
    _write_json(receipt_path, {"schema_version": SOURCE_RECEIPT_SCHEMA,
                              "content_digest": content_digest, "files": files})
    return content_digest, cache_root, sources


def _cached_registry(cache_root: Path, content_digest: str,
                     sources: list[dict]) -> dict | None:
    record = _read_json(cache_root / ("registry-" + content_digest.split(":", 1)[1] + ".json"))
    if (record and record.get("schema_version") == CACHE_SCHEMA
            and record.get("content_digest") == content_digest
            and record.get("sources") == sources
            and isinstance(record.get("registry"), dict)
            and set(record["registry"]) == {"verbs", "structure", "issues"}):
        return record["registry"]
    return None


def _literal(node):
    try:
        return json.loads(json.dumps(ast.literal_eval(node)))
    except (ValueError, TypeError):
        return None


def _name(node):
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""


def _face(text: str | None) -> str:
    text = " ".join((text or "").split())
    text = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text if len(text) <= 160 else text[:156].rsplit(" ", 1)[0] + "..."


def _imports(module, tree, walker=ast.walk):
    result = {}
    for node in walker(tree):
        if isinstance(node, ast.ImportFrom):
            base = module.split(".")[:-node.level] if node.level else []
            target = ".".join(base + ([node.module] if node.module else []))
            for alias in node.names:
                result[alias.asname or alias.name] = (target, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result[alias.asname or alias.name.split(".")[0]] = (alias.name, "")
    return result


def _source(path, node, symbol):
    return {"path": _rel(path), "symbol": symbol,
            "line": getattr(node, "lineno", 1)}


def _card(cid, face, source, *, inputs=(), outputs=(), refusals=(), test=None, command=None):
    card = {"face": face, "id": cid, "inputs": list(inputs), "outputs": list(outputs),
            "refusals": sorted(set(refusals)), "test": test,
            "descend": "python -m atlas.entry --card " + shlex.quote(cid), "source": source}
    card["command" if command else "handle"] = command or (source["path"] + "#" + source["symbol"])
    return card


def compute_registry(package: Path = PACKAGE, tests: Path | None = None) -> dict:
    tests = tests or CONTAINER / "tests"
    content_digest, cache_root, sources = _source_identity(package, tests)
    registry = _cached_registry(cache_root, content_digest, sources)
    if registry is None:
        registry = _compute_registry(package, tests, content_digest)
        _write_json(cache_root / ("registry-" + content_digest.split(":", 1)[1] + ".json"), {
            "schema_version": CACHE_SCHEMA, "content_digest": content_digest,
            "sources": sources, "registry": registry,
        })
    return copy.deepcopy(registry)


@lru_cache(maxsize=2)
def _compute_registry(package: Path, tests: Path, content_digest: str) -> dict:
    """Derive a deterministic inventory from source syntax; no tool code executes.

    Refusals follow statically named calls and imported symbols. Dynamic dispatch
    is explicitly outside that proof, rather than treated as an empty refusal set.
    """
    tests = tests or CONTAINER / "tests"
    modules, paths, imports, definitions, owners = {}, {}, {}, {}, {}
    walks: dict[int, tuple[ast.AST, ...]] = {}

    def walk(node: ast.AST) -> tuple[ast.AST, ...]:
        cached = walks.get(id(node))
        if cached is None:
            cached = tuple(ast.walk(node))
            walks[id(node)] = cached
        return cached

    source_issues = []
    for path in _files(package):
        if path.stem in {"cards", "__init__"}:
            continue
        module = "atlas." + ".".join(path.relative_to(package).with_suffix("").parts)
        try:
            tree = _tree(path)
        except (SyntaxError, UnicodeError) as exc:
            if not module.startswith("atlas.tools."):
                raise
            source_issues.append({"code": "CARD-SOURCE-UNREADABLE", "owner": module,
                                  "id": "verb:" + module.removeprefix("atlas."),
                                  "reason": type(exc).__name__})
            continue
        modules[module], paths[module] = tree, path
        imports[module] = _imports(module, tree, walk)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                definitions[module, node.name] = node
                if isinstance(node, ast.ClassDef):
                    for method in node.body:
                        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            definitions[module, node.name + "." + method.name] = method
                            owners[id(method)] = node.name
    reasons = {}
    for node in modules["atlas.errors"].body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.Assign) and any(_name(t) == "reason" for t in item.targets):
                    reasons[node.name] = _literal(item.value)

    test_refs, test_calls, test_assertions = {}, {}, {}
    for path in _files(tests):
        if path.name.startswith("test_"):
            tree = _tree(path)
            relative = _rel(path)
            test_refs[relative] = set(_imports("tests." + path.stem, tree).values())
            for test in walk(tree):
                if not isinstance(test, (ast.FunctionDef, ast.AsyncFunctionDef)) or not test.name.startswith("test_"):
                    continue
                ref = (relative, test.name)
                for node in walk(test):
                    if isinstance(node, ast.Call):
                        test_calls.setdefault(_name(node.func), []).append(ref)
                    if isinstance(node, ast.Assert):
                        for value in walk(node.test):
                            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                                test_assertions.setdefault(value.value, []).append(ref)

    def call_test(symbol):
        return next(iter(sorted(set(test_calls.get(symbol, [])))), None)

    def attach_test(card, ref, scope):
        card["test"] = ref[0] if ref else None
        card["test_scope"] = scope if ref else None
        if ref:
            card["test_node"] = "::".join(ref)

    def contract(module, symbol=None):
        direct = sorted(p for p, refs in test_refs.items()
                        if any((m == module and (symbol is None or s == symbol)) or
                               (m + "." + s == module and symbol is None) for m, s in refs))
        direct.sort(key=lambda p: (Path(p).stem != "test_" + module.rsplit(".", 1)[-1], p))
        return direct[0] if direct else None

    raised_edges: dict[tuple[str, int], tuple[frozenset[str], tuple]] = {}

    def raised(module, node):
        found, seen, queue = set(), set(), [(module, node)]
        while queue:
            current, body = queue.pop()
            key = (current, id(body))
            if key in seen:
                continue
            seen.add(key)
            cached = raised_edges.get(key)
            if cached is not None:
                direct, targets = cached
                found.update(direct)
                queue.extend(targets)
                continue
            direct, targets = set(), []
            bodies = ([n for n in body.body if isinstance(n, ast.FunctionDef) and n.name in
                       {"__init__", "__new__", "__post_init__"}] if isinstance(body, ast.ClassDef) else [body])
            for scope in bodies:
                bindings = {}
                if id(scope) in owners:
                    bindings.update({"self": (current, owners[id(scope)]), "cls": (current, owners[id(scope)])})

                def resolve(expr, context=current, depth=0):
                    if depth > 8:
                        return None
                    if isinstance(expr, ast.Name):
                        return bindings.get(expr.id) or imports[context].get(expr.id, (context, expr.id))
                    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
                        return imports[context].get(expr.value, (context, expr.value))
                    if isinstance(expr, ast.Attribute):
                        receiver = resolve(expr.value, context, depth + 1)
                        if receiver:
                            mod, symbol = receiver
                            if mod + ("." + symbol if symbol else "") in modules:
                                return (mod + ("." + symbol if symbol else ""), expr.attr)
                            if isinstance(definitions.get(receiver), ast.ClassDef):
                                return mod, symbol + "." + expr.attr
                    if isinstance(expr, ast.Call):
                        target = resolve(expr.func, context, depth + 1)
                        definition = definitions.get(target)
                        if isinstance(definition, ast.ClassDef):
                            return target
                        if isinstance(definition, (ast.FunctionDef, ast.AsyncFunctionDef)) and definition.returns:
                            return resolve(definition.returns, target[0], depth + 1)
                    return None

                # Assignments and declared parameter types supply receiver types;
                # arbitrary dynamic dispatch remains an explicit open boundary.
                if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for arg in scope.args.args + scope.args.kwonlyargs:
                        if arg.annotation and (target := resolve(arg.annotation)):
                            bindings[arg.arg] = target
                for assignment in walk(scope):
                    if isinstance(assignment, ast.Assign) and (target := resolve(assignment.value)):
                        for name in assignment.targets:
                            if isinstance(name, ast.Name):
                                bindings[name.id] = target
                for call in walk(scope):
                    if isinstance(call, ast.Raise) and isinstance(call.exc, ast.Call):
                        target = resolve(call.exc.func)
                        if target and target[0] == "atlas.errors" and target[1] in reasons:
                            direct.add(reasons[target[1]])
                    if isinstance(call, ast.Call):
                        target = resolve(call.func)
                        if target in definitions:
                            targets.append((target[0], definitions[target]))
            raised_edges[key] = frozenset(direct), tuple(targets)
            found.update(direct)
            queue.extend(targets)
        return sorted(found)

    verbs, structure, issues = [], [], list(source_issues)
    for module, tree in sorted(modules.items()):
        if not (module.startswith("atlas.tools.") or module == "atlas.entry"):
            continue
        path = paths[module]
        cid = "verb:" + module.removeprefix("atlas.")
        doc = ast.get_docstring(tree)
        description = None
        inputs, subcommands = [], []
        parser_names = {_name(t) for n in walk(tree) if isinstance(n, ast.Assign)
                        and isinstance(n.value, ast.Call) and _name(n.value.func) == "ArgumentParser"
                        for t in n.targets}
        for node in walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _name(node.func) == "ArgumentParser":
                for kw in node.keywords:
                    if kw.arg == "description":
                        description = doc if _name(kw.value) == "__doc__" else _literal(kw.value)
            if _name(node.func) == "add_parser" and node.args:
                subcommands.append(_literal(node.args[0]))
            if _name(node.func) == "add_argument":
                row = {"flags": [_literal(arg) for arg in node.args if isinstance(_literal(arg), str)],
                       "parser": ast.unparse(node.func.value)}
                for kw in node.keywords:
                    row[kw.arg] = _literal(kw.value) if _literal(kw.value) is not None else ast.unparse(kw.value)
                inputs.append(row)
        face = _face(description or doc)
        if not face:
            issues.append({"code": "CARD-FACE-MISSING", "owner": module, "id": cid,
                           "reason": "tool has no argparse description or module docstring"})
            continue
        test = contract(module)
        # A called function's test is evidence for that function, identified as
        # such in test_scope; it is never advertised as CLI coverage.
        test_scope = "tool"
        if test is None:
            called = {_name(n.func) for n in walk(tree) if isinstance(n, ast.Call)}
            candidates = sorted((s != path.stem, contract(m, s), m + "." + s)
                                for local, (m, s) in imports[module].items()
                                if local in called and not s.startswith("_") and m.startswith("atlas.") and m not in {
                                    "atlas.ids", "atlas.errors", "atlas.history", "atlas.store", "atlas.runtime"}
                                and contract(m, s))
            if candidates:
                _, test, test_scope = candidates[0]
        outputs = sorted({ast.unparse(n.value) for n in walk(tree)
                          if isinstance(n, ast.Return) and n.value is not None and not isinstance(n.value, ast.Constant)})
        effects = sorted({_name(n.func) for n in walk(tree) if isinstance(n, ast.Call)
                          and (_name(n.func).startswith(("write", "save", "export", "pour", "freeze", "bank"))
                               or _name(n.func) == "print")})
        argv = ["/usr/bin/python3", "-m", module]
        for row in inputs:
            if row["parser"] not in parser_names or not row["flags"]:
                continue
            flag = row["flags"][0]
            if row.get("required") is True or (not flag.startswith("-") and row.get("nargs") not in {"?", "*"}):
                if flag.startswith("-"):
                    argv.append(flag)
                argv.append("<" + flag.lstrip("-").replace("-", "_") + ">")
        if subcommands:
            argv.append("<" + "|".join(sorted(s for s in subcommands if isinstance(s, str))) + ">")
        card = _card(cid, face, _source(path, tree, module), inputs=inputs,
                     outputs=[{"return_expression": v} for v in outputs] + [{"effect_call": v} for v in effects],
                     refusals=raised(module, tree), test=test,
                     command=shlex.join(argv))
        card["argv"] = argv
        card["subcommands"] = sorted(s for s in subcommands if isinstance(s, str))
        card["test_scope"] = test_scope if test else None
        card["refusal_scope"] = "named calls and source-typed receivers; unresolved dynamic dispatch excluded"
        verbs.append(card)
        if test is None:
            issues.append({"code": "CARD-TEST-MISSING", "id": cid, "owner": module,
                           "reason": "no contract test imports the tool or a called operation"})

    # Kind and relation vocabulary comes from constructors and keyword calls in
    # the transition/write code. A new kind gains a stable card automatically.
    vocabulary = {}
    for module in ("atlas.state", "atlas.store"):
        loop_values = {}
        for loop in walk(modules[module]):
            if isinstance(loop, ast.For) and isinstance(loop.target, (ast.Tuple, ast.List)) and isinstance(loop.iter, (ast.Tuple, ast.List)):
                for index, target in enumerate(loop.target.elts):
                    for row in loop.iter.elts:
                        if isinstance(row, (ast.Tuple, ast.List)) and len(row.elts) > index:
                            value = _literal(row.elts[index])
                            if isinstance(value, str):
                                loop_values.setdefault(_name(target), []).append(value)
        for node in walk(modules[module]):
            if not isinstance(node, ast.Call):
                continue
            values = [(kw.arg, _literal(kw.value)) for kw in node.keywords if kw.arg in {"kind", "relation"}]
            values.extend((kw.arg, value) for kw in node.keywords if kw.arg in {"kind", "relation"}
                          for value in loop_values.get(_name(kw.value), []))
            if _name(node.func) == "ConceptricObject" and len(node.args) > 1:
                values.append(("kind", _literal(node.args[1])))
            if _name(node.func) == "GradeAxisContract" and node.args:
                values.append(("contract", _literal(node.args[0])))
            for category, value in values:
                if isinstance(value, str):
                    vocabulary.setdefault((category, value), (module, node))
    for (category, value), (module, node) in sorted(vocabulary.items()):
        label = value.replace("-", " ")
        face = (f"An Atlas object of kind {label}." if category == "kind" else
                f"An Atlas relation from its source to its target: {label}." if category == "relation" else
                f"The declared Atlas grade ordering {label}.")
        structure.append(_card("structure:" + category + ":" + value, _face(face),
                               _source(paths[module], node, value), inputs=[category], outputs=[value],
                               test=contract(module)))

    # Public record classes carry their own fields and docstrings. Include the
    # records that express generations, membership, and nested spans, plus the
    # store itself, rather than copying the design's proposed object hierarchy.
    for (module, name), node in sorted(definitions.items()):
        if isinstance(node, ast.ClassDef) and (name == "ConceptricStore" or
                (module in {"atlas.schema", "atlas.updown_history", "atlas.blueprint"} and
                 re.search(r"Generation$|MemberRef$|^Span$|^UpActReceipt$", name))):
            fields = [n.target.id for n in node.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
            face = _face(ast.get_docstring(node)) or _face("An Atlas " + re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower() + " record.")
            structure.append(_card("structure:type:" + name, face, _source(paths[module], node, name),
                                   inputs=fields, outputs=[name], refusals=raised(module, node), test=contract(module, name)))
            if name == "UpMemberRef":
                attach_test(structure[-1], call_test(name), "constructor:" + module + "." + name)
        if isinstance(node, ast.FunctionDef) and "placement" in name and not name.startswith("_") and "." not in name:
            structure.append(_card("structure:operator:" + module.removeprefix("atlas.") + "." + name,
                _face(ast.get_docstring(node)) or f"The Atlas {name.replace('_', ' ')} operation.",
                _source(paths[module], node, name), inputs=[ast.unparse(a) for a in node.args.args],
                outputs=[ast.unparse(node.returns) if node.returns else "unspecified return"],
                refusals=raised(module, node), test=contract(module, name)))
        # API-only acts also have cards: no invented CLI is attached to them.
        if isinstance(node, ast.ClassDef):
            for method in node.body:
                if module in {"atlas.store", "atlas.snapshot"} and isinstance(method, ast.FunctionDef) and re.match(r"^(read_|seal_|adopt_|reseal_|export_)", method.name):
                    face = _face(ast.get_docstring(method))
                    if face:
                        verbs.append(_card("verb:api:" + name + "." + method.name, face,
                            _source(paths[module], method, name + "." + method.name),
                            inputs=[a.arg for a in method.args.args + method.args.kwonlyargs if a.arg != "self"],
                            outputs=[ast.unparse(method.returns) if method.returns else "unspecified return"],
                            refusals=raised(module, method)))
                        attach_test(verbs[-1], call_test(method.name), module + "." + name + "." + method.name)
    for module in ("atlas.state", "atlas.store"):
        for node in walk(modules[module]):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
                continue
            message = _literal(node.exc.args[0])
            reason = reasons.get(_name(node.exc.func))
            if reason and isinstance(message, str) and re.search(r"\b(member|owner)\b", message):
                cid = "structure:refusal:" + reason + ":" + re.sub(r"[^a-z0-9]+", "-", message.lower()).strip("-")
                structure.append(_card(cid, _face(message + "."), _source(paths[module], node, _name(node.exc.func)),
                    inputs=["attempted state transition"], outputs=["refusal"], refusals=[reason]))
                ref = next(iter(sorted(set(test_assertions.get(reason, [])))), None)
                attach_test(structure[-1], ref, "reason:" + reason)
    for card in verbs:
        if card["id"] == "verb:api:ConceptricStore.read_seat_mail_frontier":
            issue = {"code": "CARD-VERB-RETIRES", "id": card["id"],
                     "owner": "CR-20260914-custody-off",
                     "reason": "custody-era, retires with CR-20260914-custody-off"}
            card["issue"] = issue
            issues.append(issue)
            continue
        if card["test"] is None and not any(i.get("id") == card["id"] for i in issues):
            issues.append({"code": "CARD-TEST-MISSING", "id": card["id"], "owner": card["source"]["path"],
                           "reason": "no contract test calls this operation"})
    issues.append({"code": "CARD-DYNAMIC-REFUSALS-UNRESOLVED", "owner": "atlas.cards",
                   "reason": "refusal lists cover named calls and source-typed receivers; unresolved dynamic dispatch remains open"})
    return {"verbs": sorted(verbs, key=lambda c: (":api:" in c["id"], c["id"])),
            "structure": sorted(structure, key=lambda c: (":type:" not in c["id"], c["id"])), "issues": issues}


def get_card(card_id: str) -> dict:
    registry = compute_registry()
    for card in registry["verbs"] + registry["structure"]:
        if card["id"] == card_id:
            return card
    raise StoreError("card id does not resolve", code="CARD-NOT-FOUND", card_id=card_id)


def card_page(field: str, offset: int = 0, limit: int = 8) -> dict:
    if field not in {"verbs", "structure", "issues"} or offset < 0:
        raise StoreError("invalid card page", code="CARD-PAGE-INVALID")
    rows = compute_registry()[field]
    selected = rows[offset:offset + limit]
    return {"field": field, "total": len(rows), "offset": offset,
            "cards": [{"face": c["face"], "id": c["id"]} for c in selected] if field != "issues" else selected,
            "descend": "python -m atlas.entry --card <id>",
            "next": f"python -m atlas.entry --cards {field} --offset {offset + limit}" if offset + limit < len(rows) else None}
