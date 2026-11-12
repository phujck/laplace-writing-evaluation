#!/usr/bin/env python3
"""Drive the VERB DOOR against a real workspace and print what a caller actually sees.

Not a test: the evidence behind the lane report's claim that one request shape works at
every altitude, that the refusal keeps the owner's house, and that the row is banked on a
caller path that has no provider turn.  It builds the harness's own empty workspace, creates
a project through the HTTP door the arrival uses, and then writes one grammar request per
act -- never an operation name.

Usage: scripts/laplace-python tools/writing_verbs/verb_door_demo.py --out <dir> [--port N]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

HARNESS = Path("/home/phujck/VScodeProjects/laplace/evidence/"
               "WRITING_RECONCILIATION_2026-10-02/harness")
TREE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(TREE / "src"))

import arrival as harness_arrival                     # noqa: E402
from _harness import Side                             # noqa: E402

from laplace.core import grammar as g                      # noqa: E402
from laplace.native import tools as wt               # noqa: E402
from laplace.native import verbs as v                # noqa: E402

PROJECT = "verb-door-demo"
PIN: dict = {}


def post(port: int, path: str, body: dict) -> dict:
    request = urllib.request.Request(
        "http://127.0.0.1:%d%s" % (port, path), method="POST",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                 "X-Laplace-Writing": "1"})
    try:
        with urllib.request.urlopen(request, timeout=120) as answer:
            return json.loads(answer.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return {"http_error": exc.code, "body": (exc.read() or b"")[:400].decode("utf-8", "replace")}


def show(label: str, request: g.Request, answer: dict, root: Path) -> dict:
    route = v.choose(request.verb, request.concept, request.payload)
    operation, payload = v.to_owner_call(request, root=root, route=route)
    print("\n--- %s" % label)
    print("  request      ", json.dumps({"verb": request.verb, "concept": request.concept,
                                         "target": request.target,
                                         "expected": list(request.expected),
                                         "payload": dict(request.payload),
                                         "by": request.by}, default=str)[:400])
    print("  owner call   ", operation, json.dumps(payload, default=str)[:220])
    print("  owner        ", route.owner, "at", route.site)
    print("  answer       ", json.dumps(answer, default=str)[:420])
    return {"label": label, "verb": request.verb, "concept": request.concept,
            "altitude": route.altitude, "operation": operation, "owner": route.owner,
            "site": route.site, "ok": bool(answer.get("ok")),
            "outcome": answer.get("outcome") or (answer.get("refused") or {}).get("kind"),
            # The owner's own sentence, VERBATIM and untruncated: a report that cites a refusal
            # must cite a file that contains it.
            "said": (answer.get("refused") or {}).get("said"),
            "raised": ((answer.get("refused") or {}).get("owner") or {}).get("raised"),
            "banked_row": answer.get("banked_row")}


def token(home: str, project: str, root: Path, ident: str = "") -> str:
    """The token of a home, or "" when the home does not exist in this project yet."""
    try:
        return str(g.identity(g.Home(home, project + ("::" + ident if ident else "")),
                              project=project, root=root))
    except Exception as exc:
        print("  (no %s token yet: %s)" % (home, str(exc)[:90]))
        return ""


def main() -> int:
    global PROJECT
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/claude-1000/recon-verbdoor")
    ap.add_argument("--work", default="/tmp/claude-1000/recon-verbdoor-work")
    ap.add_argument("--port", type=int, default=8881)
    args = ap.parse_args()
    out, work = Path(args.out), Path(args.work)
    out.mkdir(parents=True, exist_ok=True)
    sandbox = work / "sandbox"
    harness_arrival.build_empty_workspace(TREE, sandbox)
    side = Side("verbdoor", TREE, sandbox, port=args.port, state=work / "state", serve=True,
                turns={})
    rows = []
    side.start()
    try:
        made = post(args.port, "/projects/create",
                    {"kind": "paper", "name": PROJECT, "title": "Verb door demo"})
        print("project created:", json.dumps(made, default=str)[:300])
        PROJECT = (made.get("project") or made.get("name") or
                   (made.get("record") or {}).get("name") or PROJECT)
        print("project:", PROJECT)
        plan = token("plan", PROJECT, sandbox)
        network = token("concept-network", PROJECT, sandbox)
        edition = token("selected-edition", PROJECT, sandbox)
        # THE FIVE CONTENT-TREE CREATES OF SECTION 3, EACH APPLYING THROUGH THE VERB DOOR.
        # The order is the owners' own dependency order, and each step says what it had to be
        # given before it could apply -- which is the prerequisite the ROUTE does not supply,
        # because a route declares selectors and guards and no payload keys (residual 8).  The
        # tokens are re-read before every step, because each applied write moves a home.
        def read_source(payload: dict) -> dict:
            answer = wt.request(sandbox, PROJECT, "work",
                               g.Request(verb="read", concept="source-file@paragraph",
                                         target=PROJECT, payload=payload))
            return (answer.get("owner_response") or {}) if answer.get("ok") else {}

        def manuscript_dir() -> str:
            return str((read_source({}).get("document") or {}).get("manuscript_dir") or "")

        def source_files() -> list[dict]:
            """The selected manuscript's files WITH their text.

            `source {}` answers with an inventory and an empty `sources`; the text comes only
            when the read names the files (`source {files:[...]}`) -- which is itself the
            friction the grammar's `read` + target is meant to remove, and is recorded here
            rather than worked around silently."""
            inventory = [str(row.get("file")) for row in
                         (read_source({}).get("inventory") or []) if row.get("file")]
            chapters = [f for f in inventory if "/chapters/" in f] or inventory
            if not chapters:
                return []
            read = read_source({"files": chapters[:1]})
            return [row for row in (read.get("sources") or []) if row.get("file")]

        def prepare_plan() -> dict:
            """structure_change initialize -- not one of the five: the plan the plan-section
            altitude needs.  Driven through the verb door like everything else."""
            return wt.request(sandbox, PROJECT, "work", g.Request(
                verb="create", concept="plan@plan", target=PROJECT,
                expected=tuple(x for x in (token("plan", PROJECT, sandbox),
                                           token("selected-edition", PROJECT, sandbox)) if x),
                payload={"sections": [{"id": "intro", "title": "Introduction"}]}))

        five = []

        def altitude(name, needed, build):
            five.append((name, needed, build))

        altitude("chapter -- create chapter@chapter",
                 "the selected edition's token; nothing else (the owner's contract is {title})",
                 lambda: g.Request(verb="create", concept="chapter@chapter", target=PROJECT,
                                   expected=tuple(x for x in
                                                  (token("selected-edition", PROJECT,
                                                         sandbox),) if x),
                                   payload={"title": "A demonstrated chapter"}, by="eigen"))

        def plan_section():
            return g.Request(verb="create", concept="plan-section@section", target=PROJECT,
                             expected=(token("plan", PROJECT, sandbox),),
                             payload={"op": {"section": "method", "title": "Method"}})
            # NO `by`: project_structure.py:710 refuses the grammar's own request field on this
            # door (section 9, finding 6).  The probe that shows it is in `asks` below.
        altitude("plan -- create plan-section@section",
                 "an initialized plan (structure_change initialize) and op.{section,title}: "
                 "project_structure.py refuses `payload.op requires section` and then "
                 "`requires title`, which the route cannot know",
                 plan_section)

        def section():
            files = source_files()
            assert files, "no source file to insert a section into"
            row = files[0]
            raw = str(row.get("text") or "")
            return g.Request(
                verb="create", concept="section@section",
                target=PROJECT + "::" + str(row["file"]),
                # `plan-file`, not `plan`: _check_plan_guard compares against
                # state.authority.plan_revision (manuscript_structure.py:364-366), which is the
                # plan-file home; the route declares both ("plan|plan-file") and the token's own
                # home decides which value the owner is handed.
                expected=(token("plan-file", PROJECT, sandbox),
                          token("source-file", PROJECT, sandbox, ident=str(row["file"]))),
                payload={"kind": "section", "title": "A demonstrated section",
                         "source_file": str(row["file"]),
                         "after_line": len(raw.split("\n")),
                         "after_before": raw.split("\n")[-1]}, by="eigen")
        altitude("section -- create section@section",
                 "kind from the owner's enum, a source_file, and after_line (with after_before "
                 "when it is not 0): manuscript_structure.py:907-930. AND one thing the "
                 "dispatch must not supply: this door compares the guard RAW against its own "
                 "sha256:-prefixed publication (manuscript_structure.py:364-366)",
                 section)

        def claim():
            return g.Request(verb="create", concept="concept-node@claim",
                             target=PROJECT + "::result:demo",
                             expected=(token("concept-network", PROJECT, sandbox),),
                             payload={"node": "result:demo", "node_kind": "result",
                                      "essence": "A demonstrated result."}, by="eigen")
        altitude("claim -- create concept-node@claim",
                 "node, node_kind from the owner's 13-value enum, and essence: "
                 "concepts_surface add_node's contract",
                 claim)

        def block():
            files = source_files()
            assert files, "no source file to insert a block into"
            row = files[0]
            raw = str(row.get("text") or "")
            mdir = manuscript_dir()
            rel = (str(row["file"])[len(mdir) + 1:] if mdir and str(row["file"]).startswith(mdir)
                   else str(row["file"]))
            return g.Request(
                verb="create", concept="block@paragraph",
                target=PROJECT + "::" + str(row["file"]),
                payload={"clip": {"before": "A demonstrated inserted paragraph.",
                                  "kind": "paragraph"},
                         # `file` RELATIVE TO THE MANUSCRIPT DIRECTORY: manuscript_blocks._path
                         # resolves `manuscript / file` (manuscript_blocks.py:22-25), while
                         # section_change's _source_path accepts either spelling
                         # (manuscript_structure.py:295).  Two owners, two conventions, one
                         # concept -- which is the contract lane's to reconcile.
                         "destination": {"file": rel, "line": 0,
                                         "expected_source_digest":
                                             g.digest_bytes(raw.encode("utf-8"))}})
        altitude("paragraph -- create block@paragraph",
                 "a clip and a destination carrying the file, the line and that file's current "
                 "digest; block_change declares NO top-level guard, so the identity rides "
                 "inside destination (manuscript_blocks.py:172-177)",
                 block)

        prep = prepare_plan()
        print("\nprerequisite: create plan@plan ->",
              json.dumps({"ok": prep.get("ok"), "outcome": prep.get("outcome"),
                          "said": (prep.get("refused") or {}).get("said")}, default=str)[:300])
        rows.append({"label": "prerequisite: create plan@plan (not one of the five)",
                     "ok": bool(prep.get("ok")), "outcome": prep.get("outcome"),
                     "banked_row": prep.get("banked_row")})

        applied = []
        for name, needed, build in five:
            request = build()
            try:
                answer = wt.request(sandbox, PROJECT, "work", request)
            except Exception as exc:
                answer = {"ok": False, "raised": type(exc).__name__ + ": " + str(exc)[:200]}
            record = show(name, request, answer, sandbox)
            record["owner_prerequisite"] = needed
            record["one_of_the_five"] = True
            rows.append(record)
            if answer.get("ok") and answer.get("outcome") == "applied":
                applied.append(name)
        print("\nOF THE FIVE CONTENT-TREE ALTITUDES OF SECTION 3, APPLIED THROUGH THE VERB "
              "DOOR: %d/5" % len(applied))
        for name in applied:
            print("   APPLIED", name)
        for name, _needed, _build in five:
            if name not in applied:
                print("   NOT APPLIED", name)

        # THE PIN FOR THE ALTITUDE THAT DID NOT APPLY.  The same section_change call, by its
        # OLD NAME, with the guard carrying the owner's own `sha256:`-prefixed spelling instead
        # of the digest the grammar's token publishes.  If this applies, the refusal above is
        # one owner line comparing a guard raw -- not the dispatch, not the payload schema.
        pin = {"what": "section_change by its old name, guard in the owner's own spelling"}
        try:
            files = source_files()
            row = files[0]
            raw = str(row.get("text") or "")
            from laplace.manuscript.manuscript_structure import _structure_state
            state = _structure_state(PROJECT, sandbox)
            prefixed = str((state.get("authority") or {}).get("plan_revision") or "")
            pin["owner_publishes"] = prefixed
            pin["token_publishes"] = token("plan-file", PROJECT, sandbox)
            answer = wt.execute(sandbox, PROJECT, "work", "section_change", {
                "operation": "create", "kind": "section",
                "title": "A demonstrated section (owner spelling)",
                "source_file": str(row["file"]),
                "after_line": len(raw.split("\n")), "after_before": raw.split("\n")[-1],
                "expected_plan_revision": prefixed,
                "expected_source_digest": g.digest_bytes(raw.encode("utf-8"))})
            pin["applied"] = bool(answer.get("ok"))
            pin["receipt"] = (answer.get("receipt") or {}).get("id")
        except Exception as exc:
            pin["applied"] = False
            pin["refused"] = type(exc).__name__ + ": " + str(exc)[:200]
        print("\nPIN for `create section@section`:", json.dumps(pin, default=str)[:420])
        globals()["PIN"] = pin

        # The refusals the lane must still be able to show, after the five have applied.
        asks = [
            ("read the project", g.Request(verb="read", concept="project@project",
                                           target=PROJECT, payload={})),
            ("read the plan", g.Request(verb="read", concept="plan@plan", target=PROJECT,
                                        payload={})),
            # A TOKENLESS request: the refusal must name the READ for every home the ROUTE
            # declares, not only the homes the request happened to name (section 5).
            ("create a plan section with NO token at all",
             g.Request(verb="create", concept="plan-section@section", target=PROJECT,
                       expected=(), payload={"op": {"section": "x", "title": "X"}})),
            ("create a claim with NO token at all",
             g.Request(verb="create", concept="concept-node@claim",
                       target=PROJECT + "::result:tokenless",
                       expected=(), payload={"node": "result:tokenless",
                                             "node_kind": "result", "essence": "x"})),
            # The ONE span guard of the content tree, on a path with NO turn: the refusal has to
            # be the owner's own, in the owner's own house (writing_tools.py:227).
            ("change a paragraph (altitude: paragraph, one span guard, no turn)",
             g.Request(verb="change", concept="prose@paragraph",
                       target=PROJECT + "::chapters/chapter-01.tex:1-2",
                       expected=(str(g.mint("prose", PROJECT + "::chapters/chapter-01.tex:1-2",
                                            "c" * 64)),),
                       payload={"before_content": "the exact previous text", "edits": []},
                       by="eigen")),
            # A STALE token: the refusal must stay in the OWNER's house and carry `needed`.
            ("create a claim with a stale token",
             g.Request(verb="create", concept="concept-node@claim",
                       target=PROJECT + "::claim:stale",
                       expected=("rev:concept-network:%s:%s" % (PROJECT, "0" * 64),),
                       payload={"node": "claim:stale", "node_kind": "result",
                                "essence": "Stale"}, by="eigen")),
            # `by` through structure_change: the owner refuses the grammar's own request field
            # at project_structure.py:710 (section 9, finding 6).
            ("change the plan carrying by=eigen",
             g.Request(verb="create", concept="plan-section@section", target=PROJECT,
                       expected=(token("plan", PROJECT, sandbox),),
                       payload={"op": {"section": "by-probe", "title": "By probe"}},
                       by="eigen")),
        ]
        for label, request in asks:
            try:
                answer = wt.request(sandbox, PROJECT, "work", request)
            except Exception as exc:
                answer = {"ok": False, "raised": type(exc).__name__ + ": " + str(exc)[:200]}
            record = show(label, request, answer, sandbox)
            record["needed"] = (answer.get("refused") or {}).get("needed")
            record["homes_named"] = (answer.get("refused") or {}).get("homes")
            rows.append(record)
    finally:
        side.stop()
    banked = sandbox / "contract" / "talk.jsonl"
    ledger = [json.loads(line) for line in banked.read_text().splitlines()
              if line.strip()] if banked.is_file() else []
    print("\nbanked rows in %s: %d" % (banked, len(ledger)))
    for row in ledger:
        print("  ", json.dumps({k: row.get(k) for k in
                                ("record", "turn_id", "operation", "verb", "concept",
                                 "altitude", "dispatch")}, default=str))
    (out / "demo.json").write_text(json.dumps(
        {"requests": rows, "banked": ledger, "project": PROJECT,
         "five_applied": [r["label"] for r in rows if r.get("one_of_the_five") and r.get("ok")
                          and r.get("outcome") == "applied"],
         "five_not_applied": [r["label"] for r in rows if r.get("one_of_the_five")
                              and not (r.get("ok") and r.get("outcome") == "applied")],
         "pin": PIN}, indent=1, default=str))
    without_grain = [row for row in ledger if not row.get("verb")]
    print("\nbanked rows lacking verb/concept/altitude:", len(without_grain))
    print("banked rows with no turn id:", sum(1 for row in ledger if row.get("turn_id") is None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
