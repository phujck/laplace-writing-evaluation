"""Six `help` calls through the tool door, and two refusals through the HTTP door.

    scripts/laplace-python tools/help_six.py --project synthetics-foundations \
        --out <dir> [--port 8812]

The tool door is `writing_tools.execute`; there is no HTTP route that runs an arbitrary
operation (the replay harness calls it in process for the same reason), so the six help
calls go through it, from this worktree, with a real tracked project so the tokens in
`expected` are this project's own.

The two HTTP checks go to a server started from this worktree and are both REFUSALS, so
they write nothing: `POST /projects/create` with no `X-Laplace-Writing` header, and
`POST /authoring/turn` with `message` instead of `text`.  Those are exactly the arrival's
`A1-create-no-header` and `K2-turn-no-message`, the two preconditions this lane declares.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))

SIX = ("structure_change", "concept_change", "section_change", "source",
       "research_record", "note_status")
BAD = ("sha256:current", "REQUEST-example", "COPY concept.revision EXACTLY",
       "COPY logical_plan.revision EXACTLY")


def http(port: int, path: str, payload: dict, header: bool) -> dict:
    headers = {"Content-Type": "application/json"}
    if header:
        headers["X-Laplace-Writing"] = "1"
    request = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path),
                                    data=json.dumps(payload).encode(),
                                    method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as handle:
            return {"status": handle.status, "body": handle.read().decode()[:300]}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "body": exc.read().decode()[:300]}
    except OSError as exc:
        return {"status": None, "body": "%s: %s" % (type(exc).__name__, exc)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="synthetics-foundations")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    from laplace.native import tools as writing_tools

    checks: dict[str, dict] = {}
    responses: dict[str, dict] = {}
    for operation in SIX:
        response = writing_tools.execute(HERE, args.project, "work", "help",
                                        {"operation": operation})
        responses[operation] = response
        action = response["action"]
        text = json.dumps(response, ensure_ascii=False, default=str)
        expected = action.get("expected") or []
        live = [row for row in expected if row.get("token")]
        checks[operation] = {
            "generated": bool(action.get("verb") and action.get("handler")),
            "verb": action.get("verb"), "concept": action.get("concept"),
            "expected_rows": len(expected), "live_tokens": len(live),
            "sample": {"home": live[0]["home"], "asked_for_as": live[0]["asked_for_as"],
                       "read": live[0]["read"],
                       "token": live[0]["token"][:46] + "..."} if live else None,
            "rules": len(action.get("rules") or []),
            "no_requested_payload_contract": "requested_payload_contract" not in text,
            "no_owner_contract": "owner_contract" not in text,
            "no_literal_example": not any(bad in text for bad in BAD),
            "example_keys": sorted(action.get("example") or {}),
            "variant_index": sorted(action.get("variants") or {}) or None,
            "chars": len(text),
        }
    bare = writing_tools.execute(HERE, args.project, "work", "help", {})
    concept_responses = {
        row["concept"]: writing_tools.execute(
            HERE, args.project, "work", "help", {"concept": row["concept"]})
        for row in bare["concepts"]
    }
    catalogue = [row for response in concept_responses.values()
                 for row in response["catalogue"]]
    responses["(bare index)"] = bare
    responses["(concept catalogues)"] = concept_responses
    door = writing_tools.execute(HERE, args.project, "work", "help", {"door": "http"})
    responses["(http door)"] = door
    turn = writing_tools.execute(HERE, args.project, "work", "help",
                                {"route": "/authoring/turn"})
    responses["(/authoring/turn)"] = turn

    http_checks = {}
    if args.port:
        http_checks["create without the header"] = http(
            args.port, "/projects/create", {"name": "probe-declared-door"}, header=False)
        http_checks["turn with message instead of text"] = http(
            args.port, "/authoring/turn", {"project": args.project, "message": "hello"},
            header=True)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "help_six_operations.json").write_text(
        json.dumps({"project": args.project, "tool_door": checks,
                    "http_door": http_checks, "responses": responses},
                   ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for operation, row in checks.items():
        print("%-17s %s" % (operation, json.dumps(row, ensure_ascii=False)))
    print("bare index: %d concepts, %d chars; traversal: %d rows, read_one=%s"
          % (len(bare["concepts"]), len(json.dumps(bare, ensure_ascii=False)),
             len(catalogue), bare["read_one"]["payload"]))
    print("http routes declared:", [row["route"] for row in door["routes"]])
    print("/authoring/turn rules:",
          json.dumps([r for r in turn["action"]["rules"]
                      if r["rule"] in ("one-of", "enum")], ensure_ascii=False))
    for label, row in http_checks.items():
        print("HTTP %-36s -> %s %s" % (label, row["status"], row["body"][:120]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
