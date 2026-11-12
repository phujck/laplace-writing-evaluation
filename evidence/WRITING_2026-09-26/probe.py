"""Read-only audit of manuscript loading plus an isolated nested-book fixture.

Run from the checkout with scripts/laplace-python. No provider calls, compilation,
live document writes, or service changes. Prints JSON; redirect it to probes.json.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import patch

from laplace import projection_viewer, review_surface, walk
from laplace.pipeline import registry


def summary(doc):
    blocks = [b for s in doc.get("sections", []) for b in s["blocks"]]
    return {
        "ok": doc.get("ok"), "error": doc.get("error"),
        "root": doc.get("root"), "title": doc.get("title"),
        "counts": doc.get("counts"),
        "block_kinds": dict(Counter(b["kind"] for b in blocks)),
        "raw_environments": dict(Counter(b.get("env", "") for b in blocks if b["kind"] == "raw")),
        "missing": doc.get("missing"),
    }


root = Path(__file__).resolve().parents[2]
report = {
    "observed_at": datetime.now(timezone.utc).isoformat(),
    "checkout": str(root),
    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
    "scope": "fresh-process source reads; isolated parser fixture; no model or compile run",
    "source_sha256": {}, "projects": [],
}
for name in ("walk.py", "projection_viewer.py", "review_surface.py", "front_door.py", "pipeline/schema.py", "pipeline/tex_backend.py"):
    report["source_sha256"][name] = hashlib.sha256((root / "src/laplace" / name).read_bytes()).hexdigest()

for name in ("corpus-as-a-state", "subset-sum-itqde", "synthetics-genesis", "paper_falqon", "paper_roland_qrc", "free-snacks", "superarc"):
    start = time.monotonic()
    project = registry.resolve(name)
    row = {"project": name}
    try:
        row.update(summary(walk.doc(name)))
        row["seconds"] = round(time.monotonic() - start, 4)
        row["registered_tex_root"] = project.tex_root if project else None
        if project:
            row["stage_artifacts"] = {}
            for key in ("spec", "contracts", "reader_state", "narrative", "provenance", "document_model"):
                artifact = project.stage_path(key)
                row["stage_artifacts"][key] = (
                    {"json_files": sum(1 for _ in artifact.glob("*.json"))}
                    if artifact and artifact.is_dir()
                    else {"present": bool(artifact and artifact.is_file())}
                )
            tex = project.path(project.tex_root) / "main.tex"
            row["registered_root_bytes"] = tex.stat().st_size if tex.exists() else 0
            current_root = review_surface.manuscript_dir(name)
            row["walk_root_directory"] = str(current_root.relative_to(root)) if current_root else None
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    report["projects"].append(row)

with tempfile.TemporaryDirectory(prefix="laplace-writing-audit-") as tmp:
    scratch = Path(tmp)
    book = scratch / "book"
    (book / "chapters").mkdir(parents=True)
    (book / "sections").mkdir()
    (book / "main.tex").write_text("\\documentclass{book}\n\\begin{document}\n\\part{Foundations}\n\\input{chapters/one}\n\\end{document}\n")
    (book / "chapters/one.tex").write_text("\\chapter{Representation}\n\\input{sections/detail}\n")
    (book / "sections/detail.tex").write_text("\\section{Closure}\nNested section content.\n")
    with patch.object(projection_viewer, "_repo_root", return_value=scratch), patch.object(walk, "_repo_root", return_value=scratch), patch.object(review_surface, "manuscript_dir", return_value=book):
        model = projection_viewer.doc_model("book/main.tex")
        doc = walk.doc("", "book")
        body = "\n".join(b["tex"] for s in doc["sections"] for b in s["blocks"])
        report["book_fixture"] = {
            "input_files": [f["name"] for f in model["files"]],
            "nested_content_present": "Nested section content." in body,
            "heading_levels": [b["level"] for s in doc["sections"] for b in s["blocks"] if b["kind"] == "head"],
            **summary(doc),
        }

print(json.dumps(report, ensure_ascii=False, indent=2))
