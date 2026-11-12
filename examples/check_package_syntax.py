"""Syntax-only check of authored example artifacts, not candidate runtime proof."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--mode",choices=["smoke"],required=True)
p.add_argument("--args-json",required=True)
p.add_argument("--result",required=True)
a=p.parse_args()
assert json.loads(a.args_json)=={}
base=Path(__file__).resolve().parent
rows=[]
for relative in ["run_behaviours.py","behaviour_domains/__init__.py","behaviour_domains/common.py","behaviour_domains/core.py","behaviour_domains/atlas.py","behaviour_domains/reader.py","behaviour_domains/research.py","behaviour_domains/literature.py","behaviour_domains/atlas_history.py","behaviour_domains/atlas_snapshot.py","behaviour_domains/atlas_cuda.py","behaviour_domains/source.py","behaviour_domains/http.py","behaviour_domains/catalogue.py","check_package_syntax.py","behaviour_domains/source_kernel.py","behaviour_domains/source_publication.py"]:
    path=base/relative
    raw=path.read_bytes()
    compile(raw,str(path),"exec",dont_inherit=True)
    tree=ast.parse(raw)
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="PRODUCER" for t in node.targets):
            producer=ast.literal_eval(node.value)
            compile(producer,str(path)+"::PRODUCER","exec",dont_inherit=True)
    rows.append({"path":relative,"sha256":"sha256:"+hashlib.sha256(raw).hexdigest(),"syntax":"COMPILED_IN_MEMORY"})
Path(a.result).write_text(json.dumps({"scope":"Syntax only, no application import or owner execution",
    "files":rows,"count":len(rows)},indent=2)+"\n")
