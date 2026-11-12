"""The render stage's thin CLI (work kind ``render`` — always script-backed).

Regenerates the backend-owned surfaces from settled artifacts: the per-figure
environment files (from the stage-B figure specs) and the assembled main.tex
(plan order + typography profile). Deterministic; prose fragments untouched.

Usage: python scripts/render_manuscript.py [<project>] [--check]
  --check: report without writing (the contract face).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from laplace.pipeline import registry, tex_backend  # noqa: E402

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    project = args[0] if args else registry.default_project()
    if "--check" in sys.argv:
        print(json.dumps(tex_backend.render_report(project), indent=1))
        sys.exit(0)
    figs = tex_backend.write_figures_tex(project)
    tables = tex_backend.write_tables_tex(project)
    tex_backend.assemble_main_tex(project, write=True)
    print(json.dumps({"project": project, "figure_envs": [str(p) for p in figs],
                      "table_envs": [str(p) for p in tables],
                      "main": "assembled"}, indent=1))
