#!/usr/bin/env python3
"""Re-anchor `tools/writing_verbs/http_routes.csv`'s `site` column to this tree.

`gen_routes.http_rows` and this command share one scoped AST resolver. Authored
route/default semantics remain in the row; its citation is a derived coordinate.
An old line number, nearby function, comment or wrong-method route cannot settle
an ambiguous anchor. The scanner prefix guard resolves within Handler.do_POST's
actual writing-prefix/header branch. --apply updates only the measured site column.

    scripts/laplace-python tools/writing_verbs/reanchor_http_routes.py [--apply]
"""

from __future__ import annotations

import argparse
import ast
import csv
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TREE = HERE.parents[1]
CSV = HERE / "http_routes.csv"


def scoped_nodes(scope):
    """Walk one executable owner scope, excluding nested function/class bodies."""
    yield scope
    for child in ast.iter_child_nodes(scope):
        if isinstance(child, (ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda)):
            continue
        yield from scoped_nodes(child)


def _path(node):
    return (isinstance(node,ast.Name) and node.id=='path' or
            isinstance(node,ast.Attribute) and node.attr=='path'
            and isinstance(node.value,ast.Name) and node.value.id=='u')


def _header_refusal(test):
    if not (isinstance(test,ast.Compare) and len(test.ops)==1 and isinstance(test.ops[0],ast.NotEq)):
        return False
    left=test.left
    return (isinstance(left,ast.Call) and isinstance(left.func,ast.Attribute) and left.func.attr=='get'
            and isinstance(left.func.value,ast.Attribute) and left.func.value.attr=='headers'
            and isinstance(left.func.value.value,ast.Name) and left.func.value.value.id=='self'
            and len(left.args)==1 and isinstance(left.args[0],ast.Constant) and left.args[0].value=='X-Laplace-Writing'
            and len(test.comparators)==1 and isinstance(test.comparators[0],ast.Constant)
            and test.comparators[0].value=='1')


def resolve_site(tree, row, sources=None):
    """Resolve one authored HTTP anchor in its actual dispatch scope, uniquely."""
    sources = {} if sources is None else sources
    relative = row["site"].rpartition(":")[0]
    if relative not in sources:
        source=(pathlib.Path(tree)/relative).read_text(encoding="utf-8")
        sources[relative]=(source.splitlines(),ast.parse(source))
    lines,parsed=sources[relative]
    scanner=relative.endswith('/scanner.py')
    function = ('do_'+row['method'].upper()) if scanner else 'handle'
    if relative.endswith('/projection_viewer.py'):
        public=[node for node in parsed.body if isinstance(node,ast.FunctionDef) and node.name=='handle']
        delegated=[node for scope in public for node in scoped_nodes(scope) if isinstance(node,ast.Call)
                   and isinstance(node.func,ast.Name) and node.func.id=='_handle'
                   and [arg.id if isinstance(arg,ast.Name) else None for arg in node.args]==['path','query','method','body']]
        if len(public)!=1 or len(delegated)!=1:
            raise AssertionError('projection handle must uniquely delegate its unchanged request to _handle')
        function='_handle'
    if row['holds'].strip().startswith('def '):function=row['holds'].strip().split()[1].split('(')[0]
    if row.get('name')=='review/adjudicate-comment':function='_adjudicate'
    if scanner:
        factories=[node for node in parsed.body if isinstance(node,ast.FunctionDef) and node.name=='make_handler']
        classes=[node for factory in factories for node in factory.body if isinstance(node,ast.ClassDef) and node.name=='Handler']
        scopes=[node for cls in classes for node in cls.body if isinstance(node,ast.FunctionDef) and node.name==function]
    else:scopes=[node for node in parsed.body if isinstance(node,ast.FunctionDef) and node.name==function]
    if len(scopes)!=1:raise AssertionError(f"{row['name']}: missing/ambiguous HTTP owner {relative}:{function}")
    scope=scopes[0];matches=[]
    if row['holds'].strip().startswith('def '):matches=[scope.lineno]
    else:
        for node in scoped_nodes(scope):
            if not isinstance(node,ast.If):continue
            # A literal in a nearby function, comment, return or wrong route is
            # never evidence for this dispatch row.
            tests=list(ast.walk(node.test))
            if row.get('route')=='*' and scanner:
                prefix=(isinstance(node.test,ast.Call) and isinstance(node.test.func,ast.Attribute)
                        and node.test.func.attr=='startswith'
                        and _path(node.test.func.value)
                        and any(isinstance(x,ast.Constant) and x.value=='/authoring/' for x in tests))
                if not prefix:continue
                for nested in scoped_nodes(node):
                    if isinstance(nested,ast.If) and _header_refusal(nested.test):
                        if row['holds'].strip() in lines[nested.lineno-1]:matches.append(nested.lineno)
                continue
            if row.get('name')=='review/adjudicate-comment':
                test=node.test
                route_match=(isinstance(test,ast.Compare) and len(test.ops)==1 and isinstance(test.ops[0],ast.Eq)
                    and isinstance(test.left,ast.Name) and test.left.id=='verb'
                    and len(test.comparators)==1 and isinstance(test.comparators[0],ast.Constant)
                    and test.comparators[0].value=='comment')
            else:
                route_match=any(isinstance(x,ast.Compare) and len(x.ops)==1
                    and isinstance(x.ops[0],(ast.Eq,ast.In)) and _path(x.left)
                    and any(isinstance(v,ast.Constant) and v.value==row['route']
                            for c in x.comparators for v in ast.walk(c)) for x in tests)
                # The method is part of a compound route's meaning when spelled.
                method_tests=[x for x in tests if isinstance(x,ast.Compare)
                    and isinstance(x.left,ast.Name) and x.left.id=='method' and len(x.comparators)==1
                    and isinstance(x.comparators[0],ast.Constant)]
                methods=[x.comparators[0].value for x in method_tests]
                if any(len(x.ops)!=1 or not isinstance(x.ops[0],ast.Eq) for x in method_tests):route_match=False
                if methods and row['method'].upper() not in methods:route_match=False
            if route_match and row['holds'].strip() in lines[node.lineno-1]:matches.append(node.lineno)
    matches=sorted(set(matches))
    if len(matches)!=1:raise AssertionError(f"{row['name']}: missing/ambiguous HTTP anchor in {relative}:{function}: {matches}")
    return f"{relative}:{matches[0]}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    rows = list(csv.DictReader(CSV.read_text(encoding="utf-8").splitlines()))
    fields = list(rows[0].keys())
    moved, failed = [], []
    sources = {}
    for row in rows:
        rel, _, number = row["site"].rpartition(":")
        try:
            selected = resolve_site(TREE, row, sources)
        except AssertionError as error:
            failed.append((row["route"], rel, row["holds"], str(error)))
            continue
        current = int(selected.rpartition(":")[2])
        if current != int(number):
            moved.append((row["route"], rel, int(number), current))
            row["site"] = selected
    for route, rel, old, new in moved:
        print("MOVED  %-22s %s:%d -> :%d" % (route, rel, old, new))
    for route, rel, holds, why in failed:
        print("FAILED %-22s %s  %r  %s" % (route, rel, holds, why))
    if failed:
        return 2
    if not moved:
        print("every HTTP route's site already holds its text")
        return 0
    if args.apply:
        out = [",".join(fields)]
        lines = CSV.read_text(encoding="utf-8").splitlines()
        writer_rows = []
        for row in rows:
            writer_rows.append(row)
        import io
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in writer_rows:
            writer.writerow(row)
        CSV.write_text(buffer.getvalue(), encoding="utf-8")
        print("rewritten: %s" % CSV)
    else:
        print("re-run with --apply to rewrite the column")
    return 0


if __name__ == "__main__":
    sys.exit(main())
