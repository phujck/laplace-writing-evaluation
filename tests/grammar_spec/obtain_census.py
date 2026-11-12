"""Measure, on a real project, which of the 59 home kinds `identity()` can obtain.

The question a lane asks first: can I get a token for this home, or must I hold its value?
`grammar.MINT_STATUS` declares the answer; this script is the measurement that the
declaration is true, and `test_grammar.py` runs the same comparison as a test so the two
cannot drift.

Run from the tree being measured.  A git worktree carries `synthetics-foundations`, whose
registry row and 971 corpus files are tracked at HEAD:

    scripts/laplace-python evidence/WRITING_RECONCILIATION_2026-10-02/grammar/obtain_census.py \
        [project] [tree]

Exit status is 1 when the declared partition and the observed behaviour disagree.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _grammar():
    """The grammar module, installed or not.

    `laplace.core.grammar` first: once a lane has installed the module, THAT is the copy its
    suite must measure.  Only then the file beside this script.  A plain `import grammar`
    is not enough on its own --- a sibling directory named `grammar/` on `sys.path` imports
    as an empty namespace package and shadows the real module, which is exactly what
    happened the first time this packet's own INSTALL was run.
    """
    try:
        from laplace.core import grammar as mod    # type: ignore
        if hasattr(mod, "HOME_KINDS"):
            return mod
    except Exception:
        pass
    sys.path.insert(0, str(HERE))
    import grammar as mod                     # type: ignore
    assert hasattr(mod, "HOME_KINDS"), (
        "%r is not the grammar module; a directory named `grammar` is shadowing it"
        % (getattr(mod, "__file__", mod),))
    return mod


g = _grammar()


def manuscript_dir(project: str, tree: Path) -> Path:
    """The project's manuscript directory, from the registry row the owners read."""
    rows = json.loads((tree / "registry_projects.json").read_text())["projects"]
    row = next((r for r in rows if r.get("name") == project), None)
    if row is None:
        raise LookupError("%s is not registered in %s" % (project, tree))
    return tree / str(row.get("tex_root") or "")


def ids_for(kind: str, project: str, tree: Path) -> str:
    """A real home id of this kind in this project.

    A recipe-B home is identified by a PATH, so handing it the project name is a test
    error, not a missing mint rule: the 11 B homes all mint when given a file that exists.
    """
    base = manuscript_dir(project, tree)
    tex = sorted(p for p in base.glob("*.tex") if p.is_file())
    a_file = (tex[0] if tex else base / "authoring.json").relative_to(tree).as_posix()
    a_json = (base / "authoring.json").relative_to(tree).as_posix()
    byte_homes = {"source-file": a_file, "block": a_file, "prose": a_file,
                  "section": a_file, "heading": a_file, "chapter": a_file,
                  "repository-file": a_json, "guide-document": a_json,
                  "artifact": a_json, "producer": a_json, "reference-text": a_json}
    if kind in byte_homes:
        return project + "::" + byte_homes[kind]
    if kind == "reference":
        references = json.loads((base / "references.json").read_text(encoding="utf-8"))
        rows = references.get("associations") or []
        if rows and isinstance(rows[0], dict) and rows[0].get("key"):
            return project + "::" + str(rows[0]["key"])
    return project


def census(project: str, tree: Path) -> dict:
    """Run identity() over every home kind and bucket what happened."""
    sys.path.insert(0, str(tree / "src"))
    minted, unwired, absent, mismatch = [], [], [], []
    for kind in g.HOME_KINDS:
        home = g.Home(kind, ids_for(kind, project, tree))
        declared = g.MINT_STATUS[kind]
        try:
            token = g.identity(home, project=project, root=tree)
        except NotImplementedError as exc:
            unwired.append((kind, str(exc).split(". ")[0]))
            if declared != "caller-value":
                mismatch.append((kind, declared, "NotImplementedError"))
        except Exception as exc:
            absent.append((kind, "%s: %s" % (type(exc).__name__, str(exc)[:140])))
            if declared != "read":
                mismatch.append((kind, declared, "wired read raised %s"
                                 % type(exc).__name__))
        else:
            minted.append((kind, str(token)))
            if declared != "read":
                mismatch.append((kind, declared, "minted"))
    return {"project": project, "tree": str(tree), "minted": minted,
            "unwired": unwired, "absent": absent, "mismatch": mismatch,
            "total": len(g.HOME_KINDS)}


def main(argv: list[str]) -> int:
    project = argv[1] if len(argv) > 1 else "synthetics-foundations"
    tree = Path(argv[2]) if len(argv) > 2 else Path(__file__).resolve().parents[3]
    r = census(project, tree)
    print("project %s   tree %s" % (r["project"], r["tree"]))
    print("OBTAINED FROM THE HOME ALONE: %d of %d" % (len(r["minted"]), r["total"]))
    for kind, token in r["minted"]:
        print("   %-20s %s" % (kind, token[:92]))
    print("NEEDS A CALLER VALUE: %d  (%d with no read wired, %d wired but the home does "
          "not exist in this project)"
          % (len(r["unwired"]) + len(r["absent"]), len(r["unwired"]), len(r["absent"])))
    for kind, why in r["unwired"] + r["absent"]:
        print("   %-20s %s" % (kind, why))
    print("DECLARED MINT_STATUS vs OBSERVED: %d mismatches" % len(r["mismatch"]))
    for row in r["mismatch"]:
        print("   MISMATCH %s declared=%s observed=%s" % row)
    print(json.dumps({"minted": len(r["minted"]), "unwired": len(r["unwired"]),
                      "wired_but_absent": len(r["absent"]), "total": r["total"],
                      "declared_read": len(g.OBTAINABLE),
                      "declared_caller_value": len(g.CALLER_VALUE),
                      "mismatches": len(r["mismatch"])}))
    return 1 if r["mismatch"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
