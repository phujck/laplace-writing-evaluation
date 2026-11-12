#!/usr/bin/env python3
"""Verify a real evaluation image, with a NEW named volume and no host mounts.

Run on a Docker host: python3 verify_image.py --image IMAGE --output NEW_DIRECTORY
Use --pull for a fresh anonymous pull with an empty HOME/DOCKER_CONFIG. No model,
provider or authentication action is performed. Evidence and owned volume remain
on failure; --keep also retains a successful container/volume for inspection.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def request(base, path):
    with urllib.request.urlopen(base + path, timeout=90) as response:
        raw = response.read()
        return json.loads(raw) if "json" in response.headers.get("Content-Type", "") else raw


def inside(args):
    """This code is delivered by docker exec stdin; imports are image-installed."""
    from urllib.parse import urlencode
    seed, root = Path(args.seed).resolve(), Path(args.workspace).resolve()
    out = root / "container-verification"
    out.mkdir(exist_ok=True)
    report = {"schema": "laplace.evaluation-image-proof/1", "phase": args.phase,
              "checks": [], "models_or_providers_called": False}

    def save(name, value):
        (out / (name + ".json")).write_text(json.dumps(value, indent=2, default=str) + "\n")
        return value

    def checked(name, **values):
        report["checks"].append({"check": name, **values})

    def get(route, **query):
        return request("http://127.0.0.1:8771", route + ("?" + urlencode(query) if query else ""))

    try:
        if args.phase == "pins":
            manifest = json.loads((seed / "release/selection-manifest.json").read_text())
            bootstrap = json.loads((root.parent / "evaluation-workspace.json").read_text())
            import tomllib
            runtime = tomllib.loads((root / "runtime_profiles.toml").read_text())["lifecycle"]
            import platform
            assert bootstrap["seed_manifest_sha256"] == digest(seed / "release/selection-manifest.json")
            assert bootstrap["runtime_setup"]["source_sha256"] == digest(seed / "runtime_profiles.toml")
            assert bootstrap["runtime_setup"]["configured_sha256"] == digest(root / "runtime_profiles.toml")
            assert bootstrap["runtime_setup"]["python"] == sys.executable == runtime["python"]
            assert runtime["expected_python"] == platform.python_version()
            assert bootstrap["providers_started"] == 0
            rows = list(manifest["files"])
            rows += [{"path": name, **row} for name, row in manifest.get("derived_files", {}).items()]
            checked_paths = set()
            for row in rows:
                path = row["path"]
                for base in (seed, root):
                    target = (base / path).resolve()
                    assert target.is_relative_to(base), path
                    expected = (bootstrap["runtime_setup"]["configured_sha256"]
                                if base == root and path == "runtime_profiles.toml" else row["sha256"])
                    assert target.is_file() and digest(target) == expected, (str(base), path)
                    if "bytes" in row:
                        if not (base == root and path == "runtime_profiles.toml"):
                            assert target.stat().st_size == row["bytes"], path
                checked_paths.add(path)
            checked("all selected and derived seed/workspace files match declared pins",
                    unique_paths=len(checked_paths), manifest_sha256=digest(seed / "release/selection-manifest.json"),
                    exact_declared_runtime_overlay=bootstrap["runtime_setup"])
            # Full image source includes Atlas implementation, tests, and packaged fixture.
            import laplace, atlas
            from atlas.record.ingest import toy
            installed_fixture = toy.load_fixture()
            checked("installed Atlas fixture loads", typed_rows=len(installed_fixture.ROWS),
                    loader=str(Path(toy.__file__).resolve()), loader_sha256=digest(toy.__file__))
            assert len(installed_fixture.ROWS) == 10, len(installed_fixture.ROWS)
            atlas_sources = list((seed / "src/atlas").rglob("*.py"))
            assert len(atlas_sources) >= 147, len(atlas_sources)
            assert not Path(laplace.__file__).resolve().is_relative_to(seed)
            assert not Path(atlas.__file__).resolve().is_relative_to(seed)
            checked("application installed independently of seed", laplace=laplace.__file__, atlas=atlas.__file__,
                    atlas_source_modules=len(atlas_sources))
            for command in ("codex", "claude", "pdflatex", "bibtex", "dot", "pdftoppm"):
                version_flag = "-V" if command == "dot" else ("-v" if command == "pdftoppm" else ("-version" if command in ("pdflatex", "bibtex") else "--version"))
                proc = subprocess.run([command, version_flag],
                                      capture_output=True, text=True, timeout=30)
                assert proc.returncode == 0, (command, proc.stdout, proc.stderr)
                checked("bundled executable version only", command=command,
                        output=(proc.stdout + proc.stderr).splitlines()[:3])

        if args.phase in ("owners", "cold"):
            from laplace.native import tools
            from laplace.writing import records
            from laplace.manuscript import manuscript_source
            health = get("/authoring/health")
            assert health.get("active_runs") == 0, health
            projects = get("/authoring/projects")["projects"]
            ids = {p["id"] for p in projects}
            required = {"memory-in-pieces", "eigen-technical-due-diligence-briefing",
                        "adaptive-normal-form-aek9", "self-consistent-loss-geometries-coupled-evaluators",
                        "behaviour-example"}
            assert ids == required or (args.phase == "cold" and required < ids), ids
            checked("four manuscripts and genuine behaviour project available", projects=sorted(ids))
            manifest = json.loads((seed / "release/selection-manifest.json").read_text())
            for paper in manifest["papers"]:
                project = paper["project"]
                doc = get("/walk/doc", corpus=project)
                assert doc.get("ok") and doc.get("citations") and doc.get("refs"), (project, doc.keys())
                assert not doc.get("citations_note") and not doc.get("refs_note"), project
                pdf = get("/projection/pdf", file=paper["pdf"], corpus=project)
                assert hashlib.sha256(pdf).hexdigest() == paper["final_build"]["outputs"][paper["pdf"]], project
                blocks = [block for section in doc.get("sections", []) for block in section.get("blocks", [])]
                image_routes = sorted({image["route"] for block in blocks
                                       for image in block.get("images", []) if image.get("route")})
                missing_images = [image for block in blocks for image in block.get("images", [])
                                  if not image.get("exists") or not image.get("route")]
                assert not missing_images, (project, missing_images)
                assert image_routes, (project, "No actual figure route discovered")
                for route in image_routes:
                    assert route.startswith("/") and not route.startswith("//"), route
                    served = request("http://127.0.0.1:8771", route)
                    assert isinstance(served, bytes) and len(served) > 100, route
                source = manuscript_source.resolve(project, repo_root=root)
                source_files = tools.execute(root, project, "work", "source", {"files": [source["root"]]})
                assert source_files.get("sources") and source_files["sources"][0].get("text"), project
                catalogue = get("/research/state", project=project, view="summary")
                save("research-" + project, catalogue)
                assert not catalogue.get("records_error") and catalogue.get("results"), (project, catalogue)
                current_results = sum(row.get("currentness") == "CURRENT" for row in catalogue["results"])
                assert current_results > 0, (project, catalogue["results"])
                checked("canonical manuscript HTTP reader, bibliography and exact PDF", project=project,
                        refs=len(doc["refs"]), citations=len(doc["citations"]), pdf_bytes=len(pdf),
                        actual_figure_routes_served=image_routes, current_research_results=current_results)
            project = "behaviour-example"
            doc = get("/walk/doc", corpus=project)
            assert doc.get("ok") and len(json.dumps(doc)) > 1000, doc
            src = manuscript_source.resolve(project, repo_root=root)
            main = root / src["root"]
            assert main.is_file() and main.stat().st_size > 50, src
            style = tools.execute(root, project, "work", "writing_style", {"view": "profile"})
            save("demo-style", style)
            assert "public-demo-v1" in json.dumps(style) and len(json.dumps(style)) > 350
            detail = get("/work/state", project=project, view="detail", id="WORK-example")
            save("demo-work", detail)
            assert detail["task"]["status"].lower() == "done", detail["task"]
            # Actual Work owner standing, never infer acceptance from text in a conversation.
            review = get("/work/state", project=project, view="review", id="WORK-example",
                         phase_id="PHASE-75f0760033cdaf1f56e477cb",
                         phase_revision="sha256:14a2b058097d4aee04cd9effde2afbab4b52b203fe98d7b969f1aba56fe6317f")
            save("demo-independent-review", review)
            assert "ACCEPT" in json.dumps(review) and "INDEPENDENT" in json.dumps(review), review
            overview = tools.execute(root, project, "work", "structure", {})
            section_ids = [row["id"] for row in overview["reader_plan"]["sections"]]
            assert section_ids
            structure = tools.execute(root, project, "work", "structure", {"view": "detail", "section_ids": section_ids})
            save("demo-reader", structure)
            assert structure.get("sections"), structure
            section = structure["sections"][0]
            assert section.get("reader_transition") and section.get("paragraph_plan"), section
            assert section["reader_transition"]["input_currentness"]["status"] == "CURRENT", section["reader_transition"]
            paragraphs = section["paragraph_plan"]["paragraphs"]["items"]
            assert paragraphs and all(row["input_currentness"]["status"] == "CURRENT" for row in paragraphs), paragraphs
            research = get("/research/state", project=project, view="summary")
            save("demo-research", research)
            assert research["state"] == "COMPLETE" and research.get("results"), research
            assert all(row.get("currentness") == "CURRENT" for row in research["results"]), research["results"]
            for row in research["results"]:
                result = tools.execute(root, project, "work", "research", {"view": "result", "id": row["id"]})
                save("demo-research-result-" + row["id"].replace(":", "-"), result)
            # Resolve/hydrate genuine stored rows through the actual records/body owners.
            from laplace.work import history
            with records.index_lock:
                index = records.index(root)
                rows = [dict(row) for row in index.rows if row.get("project") == project]
                kinds = {kind: sum(row.get("record") == kind for row in rows)
                         for kind in ("writing-session", "writing-turn", "writing-reply", "writing-application")}
            assert all(kinds.values()), kinds
            hydrated = []
            for kind in ("writing-turn", "writing-reply", "writing-application"):
                meta = next(row for row in rows if row.get("record") == kind)
                body = history.record(project, "activity:journal:" + meta["id"], root)
                assert body.get("record") and not body.get("custody_errors"), body
                served = get("/authoring/history", project=project, view="record", id="activity:journal:" + meta["id"])
                assert served["record"] == body["record"]
                hydrated.append({"kind": kind, "id": meta["id"], "resolved_bytes": len(json.dumps(body))})
            folds = records.fold_records(root)
            sessions = [s for s in folds["sessions"].values() if s.get("project") == project]
            assert sessions and all(not s.get("native_session_id") for s in sessions), sessions
            checked("genuine conversation/actions/proposal/application bodies remain readable, resume authority detached",
                    row_counts=kinds, hydrated=hydrated)
            summary = json.dumps(detail)
            assert "PHASE-4a27c19da7afb99095e77c9d" in summary, "latest synthesis missing from Work"
            checked("Work DONE with actual accepted independent return and parent synthesis")
            # All explicit visual PDFs in current source closure are nonempty and linked by real selected files.
            figures = [row for row in manifest["files"] if row["path"].endswith((".pdf", ".svg", ".png"))
                       and ("figure" in row["path"] or "illustration" in row["path"])]
            assert len(figures) >= 9, len(figures)
            checked("at least nine actual selected visual assets survive", count=len(figures))
            if args.phase == "cold":
                browser_state = json.loads((out / "browser-state.json").read_text())
                target = root / browser_state["file"]
                assert digest(target) == browser_state["restored_sha256"], target
                # New HTTP document and source owner read after NEW process, same named volume.
                reopened = get("/walk/doc", corpus=browser_state["project"])
                assert reopened.get("ok")
                checked("disposable UI project exact restored source persists after cold container recreation",
                        project=browser_state["project"], file=browser_state["file"], sha256=digest(target))

        if args.phase == "examples":
            import laplace
            package_root = str(Path(laplace.__file__).resolve().parent.parent)
            target = Path(tempfile.mkdtemp(prefix="container-examples-")) / "run"
            cmd = [sys.executable, "-B", "-s", str(seed / "examples/run_behaviours.py"),
                   "--output", str(target), "--package-root", package_root, "--candidate-root", str(seed)]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
            (out / "nine-groups.log").write_text(proc.stdout)
            assert proc.returncode == 0, proc.stdout[-6000:]
            result = json.loads((target / "evidence/summary.json").read_text())
            save("nine-groups", result)
            assert len(result["groups"]) == 9 and all(x["status"] == "EXECUTED" for x in result["groups"].values())
            checked("nine model-free local owner groups execute in fresh isolated fixture", groups=list(result["groups"]))
            script = seed / "writing_projects/memory-in-pieces/evidence/DYNAMIC_MEMORY_DEMO_2026-11-11/incremental_demo_checked.py"
            demo_out = Path(tempfile.mkdtemp(prefix="container-rss-")) / "result.json"
            proc = subprocess.run([sys.executable, str(script), "--mode", "smoke", "--args-json", "{}", "--result", str(demo_out)],
                                  capture_output=True, text=True, timeout=180, cwd=seed)
            (out / "rss-demo.log").write_text(proc.stdout + proc.stderr)
            assert proc.returncode == 0 and demo_out.is_file(), proc.stderr[-5000:]
            demo = json.loads(demo_out.read_text())
            save("rss-demo", demo)
            checked("bounded Dynamic Memory RSS smoke executed without models", result_sha256=digest(demo_out), result_bytes=demo_out.stat().st_size)

        if args.phase == "tex":
            from laplace.native import tools
            # Full self-contained disposable COPY, not a host mount or mutation to published source.
            temp = Path(tempfile.mkdtemp(prefix="container-canonical-tex-")) / "workspace"
            shutil.copytree(seed, temp)
            project = "adaptive-normal-form-aek9"
            os.environ["LAPLACE_REPO_ROOT"] = str(temp)
            os.environ["LAPLACE_STATE"] = str(temp / ".verification-state")
            from laplace.manuscript import manuscript_source
            source = manuscript_source.resolve(project, repo_root=temp)
            root_tex = temp / source["root"]
            removed_outputs = []
            for extension in (".pdf", ".aux", ".bbl", ".blg", ".fls", ".fdb_latexmk", ".log", ".synctex.gz"):
                target = root_tex.with_suffix(extension)
                if target.is_file():
                    removed_outputs.append({"path": str(target.relative_to(temp)), "sha256": digest(target)})
                    target.unlink()
            save("canonical-disposable-outputs-removed", removed_outputs)
            build = tools.execute(temp, project, "work", "build", {})
            save("canonical-build-start", build)
            deadline = time.monotonic() + 240
            while True:
                state = tools.execute(temp, project, "work", "build_status", {})
                save("canonical-build-status", state)
                if not state.get("running") and state.get("state") not in ("running", "cancelling"):
                    break
                assert time.monotonic() < deadline, state
                time.sleep(.5)
            assert state.get("ok") and state.get("fresh"), state
            pdf = root_tex.with_suffix(".pdf")
            assert pdf.is_file() and pdf.read_bytes().startswith(b"%PDF"), pdf
            assert root_tex.with_suffix(".fls").is_file(), "actual TeX recorder output missing"
            shutil.copy2(pdf, out / "canonical-rebuilt.pdf")
            for suffix in (".fls", ".log", ".bbl"):
                target = root_tex.with_suffix(suffix)
                if target.is_file():
                    shutil.copy2(target, out / ("canonical-rebuilt" + suffix))
            checked("actual canonical manuscript compiled through installed build owner", project=project,
                    pdf_sha256=digest(pdf), pdf_bytes=pdf.stat().st_size, build=state)
        report["status"] = "PASS"
    except BaseException as exc:
        report["status"] = "FAIL"
        report["error"] = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        save("phase-" + args.phase, report)
        print(json.dumps(report, default=str))


def host(args):
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    token = uuid.uuid4().hex[:12]
    volume, container = "evaluation-proof-" + token, "evaluation-proof-" + token
    report = {"image": args.image, "volume": volume, "container": container, "phases": [],
              "models_or_providers_called": False, "host_repository_mounts": False}
    docker_env = os.environ.copy()
    anonymous = None

    def run(argv, *, input=None, timeout=600):
        proc = subprocess.run(argv, input=input, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, env=docker_env, timeout=timeout)
        (output / ("command-%02d.log" % len(list(output.glob("command-*.log"))))).write_text(proc.stdout)
        assert proc.returncode == 0, (argv, proc.returncode, proc.stdout[-8000:])
        return proc.stdout

    def launch():
        run(["docker", "run", "-d", "--name", container, "--network", "bridge",
             "-p", "127.0.0.1::8771", "--mount", "type=volume,source=" + volume + ",target=/data", args.image])
        info = json.loads(run(["docker", "inspect", container]))[0]
        assert len(info["Mounts"]) == 1 and info["Mounts"][0]["Type"] == "volume", info["Mounts"]
        port = info["NetworkSettings"]["Ports"]["8771/tcp"][0]["HostPort"]
        base = "http://127.0.0.1:" + port
        deadline = time.monotonic() + 180
        while True:
            try:
                health = request(base, "/authoring/health")
                if health.get("active_runs") == 0:
                    break
            except OSError:
                pass
            assert time.monotonic() < deadline, run(["docker", "logs", container])[-8000:]
            time.sleep(.5)
        return base

    def probe(phase):
        value = run(["docker", "exec", "-i", container, "python", "-", "--inside", "--phase", phase,
                     "--seed", args.seed, "--workspace", "/data/workspace"], input=Path(__file__).read_text(), timeout=900)
        report["phases"].append(phase)
        return value

    try:
        if args.pull:
            anonymous = tempfile.TemporaryDirectory(prefix="evaluation-anonymous-")
            home = Path(anonymous.name)
            (home / "docker").mkdir()
            docker_env.update(HOME=str(home), DOCKER_CONFIG=str(home / "docker"))
            docker_env.pop("DOCKER_AUTH_CONFIG", None)
            run(["docker", "pull", args.image], timeout=1800)
            report["anonymous_pull"] = {"empty_home": True, "empty_docker_config": True, "auth_supplied": False}
        report["image_inspect"] = json.loads(run(["docker", "image", "inspect", args.image]))[0]
        run(["docker", "volume", "create", volume])
        base = launch()
        for phase in ("pins", "owners", "examples", "tex"):
            probe(phase)
        browser = Path(__file__).with_name("verify_browser.mjs")
        run(["docker", "exec", "-i", container, "node", "--input-type=module", "-", "http://127.0.0.1:8771"],
            input=browser.read_text(), timeout=180)
        report["phases"].append("browser-save-undo-reopen")
        run(["docker", "stop", "-t", "20", container])
        run(["docker", "rm", container])
        base = launch()
        probe("cold")
        run(["docker", "cp", container + ":/data/workspace/container-verification", str(output / "container-evidence")])
        report["status"] = "PASS"
    except BaseException as exc:
        report["status"] = "FAIL"
        report["error"] = type(exc).__name__ + ": " + str(exc)
        subprocess.run(["docker", "cp", container + ":/data/workspace/container-verification", str(output / "container-evidence")], capture_output=True)
        raise
    finally:
        logs = subprocess.run(["docker", "logs", container], capture_output=True, text=True)
        (output / "server.log").write_text(logs.stdout + logs.stderr)
        if not args.keep and report.get("status") == "PASS":
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            subprocess.run(["docker", "volume", "rm", volume], capture_output=True)
            report["owned_container_and_volume_removed"] = True
        else:
            subprocess.run(["docker", "stop", "-t", "20", container], capture_output=True)
            report["owned_stopped_container_and_volume_retained"] = True
        if anonymous:
            anonymous.cleanup()
        (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k != "image_inspect"}, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image")
    p.add_argument("--output")
    p.add_argument("--pull", action="store_true")
    p.add_argument("--keep", action="store_true")
    p.add_argument("--seed", default="/opt/evaluation/seed")
    p.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--phase", choices=("pins", "owners", "examples", "tex", "cold"))
    p.add_argument("--workspace", default="/data/workspace", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.inside:
        assert args.phase
        return inside(args)
    if not args.image or not args.output:
        p.error("--image and --output are required")
    host(args)


if __name__ == "__main__":
    main()
