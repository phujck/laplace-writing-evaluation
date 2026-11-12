#!/usr/bin/env python3
"""Model-free examples. Run with the candidate's installed Python, never Main."""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import traceback

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", "--workspace", dest="output", type=Path, required=True)
    p.add_argument("--package-root", type=Path, required=True,
                   help="Candidate-installed package parent (site-packages, not Main)")
    p.add_argument("--groups", default="core,reader,research,literature,source,atlas,source_kernel,http,catalogue",
                   help="Comma-separated domain modules. atlas_cuda requires explicit selection.")
    p.add_argument("--candidate-root", type=Path, default=Path(__file__).resolve().parents[1],
                   help="Candidate tree used only for public catalogue source coordinates")
    a = p.parse_args()
    package_root = a.package_root.expanduser().resolve(strict=True)
    groups = [g.strip() for g in a.groups.split(",")]
    allowed = {"core", "atlas", "reader", "research", "literature", "source", "http", "catalogue", "atlas_cuda", "source_kernel", "source_publication"}
    if not groups or len(groups) != len(set(groups)) or any(g not in allowed for g in groups):
        p.error("Groups must be unique supported domain module names")
    if any(g in groups for g in ("reader", "research", "literature", "source", "http")) and groups[0] != "core":
        p.error("Project-domain examples require core as the first group in a new output")
    root = a.output.expanduser().absolute()
    if root.is_symlink() or any(x.is_symlink() for x in root.parents):
        p.error("Output and ancestors must not be symlinks")
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        p.error("Output must be new or an empty directory, never an existing workspace")
    if any((parent/".git").exists() for parent in (root, *root.parents)):
        p.error("Output must be outside source checkouts, including Main and the candidate")
    for name in ("LAPLACE_STATE", "LAPLACE_SESSION_WORKSPACES"):
        if os.environ.get(name) and root.is_relative_to(Path(os.environ[name]).expanduser().resolve()):
            p.error("Output must not be inside inherited application state")
    if "source_publication" in groups and (
        "source_kernel" not in groups or groups.index("source_kernel") > groups.index("source_publication")):
        p.error("source_publication requires source_kernel earlier in the same new output")
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    # This must happen before any application import. No inherited credentials/state.
    keep = {"PATH", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR", "LD_LIBRARY_PATH"}
    env = {k: v for k, v in os.environ.items() if k in keep}
    for name in ("home", "state", "cache", "config", "tmp"):
        (root / name).mkdir()
    env.update(HOME=str(root/"home"), XDG_STATE_HOME=str(root/"state"),
               XDG_CACHE_HOME=str(root/"cache"), XDG_CONFIG_HOME=str(root/"config"),
               TMPDIR=str(root/"tmp"), MPLCONFIGDIR=str(root/"config"/"matplotlib"),
               LAPLACE_STATE=str(root/"state"), LAPLACE_REPO_ROOT=str(root/"workspace"),
               LAPLACE_SESSION_WORKSPACES=str(root/"state"/"workspaces"),
               PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    os.environ.clear()
    os.environ.update(env)
    sys.dont_write_bytecode = True
    # Deny network in this process. Producer children have their own explicit argv,
    # no credentials, and use only the supplied deterministic local script.
    def no_network(event, args):
        if event == "socket.connect":
            address = args[1]
            if not isinstance(address, tuple) or address[0] not in ("127.0.0.1", "::1"):
                raise RuntimeError("Examples permit only explicit loopback connections")
        if event == "socket.getaddrinfo" and args[0] not in ("127.0.0.1", "::1"):
            raise RuntimeError("Examples do not perform remote name resolution")
    sys.addaudithook(no_network)
    (root/"workspace"/"profiles").mkdir(parents=True)
    (root/"workspace"/"registry_projects.json").write_text('{"projects": []}\n')
    (root/"workspace"/"profiles"/"writing_sources.json").write_text(
        '{"repositories":{"laplace":"."}}\n')
    style_resource = Path(__file__).resolve().parent/"resources"/"visual_style.json"
    style_bytes = style_resource.read_bytes()
    if hashlib.sha256(style_bytes).hexdigest() != "affb3c753536104dfe1fa687e8cef5c5db0fd26d8b5e95c3481de51d95ab230e":
        p.error("The explicitly selected public visual style resource changed")
    (root/"workspace"/"profiles"/"visual_style.json").write_bytes(style_bytes)
    (root/"evidence").mkdir()
    # Explicit bootstrap also works with Python -I / safe-path mode.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from behaviour_domains.common import Recorder
    import laplace, atlas
    origins = {m.__name__: {"path": str(Path(m.__file__).resolve()),
                "sha256": hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()}
               for m in (laplace, atlas)}
    recorder = Recorder(root)
    recorder.candidate_root = a.candidate_root.resolve(strict=True)
    recorder.package_root = package_root
    for module in (laplace, atlas):
        if not Path(module.__file__).resolve().is_relative_to(package_root):
            p.error("Wrong imported package origin: " + str(module.__file__))
    os.chdir(root/"workspace")
    results = {}
    for group in groups:
        try:
            module = importlib.import_module("behaviour_domains." + group)
            results[group] = module.run(root/"workspace", recorder)
        except Exception as exc:
            results[group] = {"status": "FAILED", "error": repr(exc),
                              "traceback": traceback.format_exc()}
        recorder.save("group-" + group, results[group])
    loaded = {name: str(Path(module.__file__).resolve()) for name, module in sys.modules.items()
              if (name in ("laplace", "atlas") or name.startswith(("laplace.", "atlas.")))
              and getattr(module, "__file__", None)}
    outside = {name: path for name, path in loaded.items()
               if not Path(path).is_relative_to(package_root)}
    if outside:
        results["origin_boundary"] = {"status":"FAILED","outside_package_root":outside}
    recorder.save("module-origins", loaded)
    summary = {"schema_version": "laplace.behaviour-examples/1",
        "status": "FAILED" if any(v.get("status") == "FAILED" for v in results.values()) else "FINITE_GROUPS_EXECUTED",
        "qualification": "Actual local owner calls on authored synthetic inputs. Not provider replies, independent review, scientific acceptance, or complete behavioural coverage.",
        "python": sys.version, "executable": sys.executable, "origins": origins,
        "root": str(root), "groups": results,
        "provider_execution": "NOT_RUN: separate explicit subscription admission required",
        "standard_tier": {"provider": "codex", "model": "gpt-6.1-sol", "effort": "high",
                          "qualification": "requested configuration, not an observed provider execution"}}
    recorder.save("summary", summary)
    print(json.dumps(summary, indent=2, default=str))
    return 1 if summary["status"] == "FAILED" else 0

if __name__ == "__main__":
    raise SystemExit(main())
