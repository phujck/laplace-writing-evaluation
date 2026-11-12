"""Render archived memory controls and publish the three inspected conceptual figures.
No original input or manuscript source is overwritten. Output is run-isolated.
"""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
p=argparse.ArgumentParser()
p.add_argument("--mode",required=True);p.add_argument("--args-json",required=True);p.add_argument("--result",required=True)
a=p.parse_args()
assert a.mode=="smoke" and json.loads(a.args_json)=={}
root=Path.cwd()
out=root/"manuscript"/"working-draft"/"figures"/("completion-"+Path(a.result).stem)
out.mkdir(parents=True,exist_ok=False)
data=json.loads((root/"evidence-snapshots/memory/reader-relational-controls-20261015.json").read_text())
plt.rcParams.update({"font.family":"DejaVu Serif","font.size":9,"mathtext.fontset":"dejavuserif","pdf.fonttype":42,"svg.fonttype":"none","axes.spines.top":False,"axes.spines.right":False})
fig,axes=plt.subplots(1,2,figsize=(6.4,3.3),sharey=True)
cols=["#009E73","#0072B2","#E69F00"]
for ax,name,title in zip(axes,["overall","temporal"],["(a) All LongMem questions","(b) Temporal-reasoning subset"]):
    row=data[name];x=np.arange(3)
    vals=np.array(row["correct"])/row["total"]
    ax.bar(x,vals,color=cols,width=.62)
    ax.set_xticks(x,["Memory","Dense","Hybrid"])
    ax.set_ylim(0,1.04)
    ax.set_title(title,fontsize=10,pad=12)
    for i,(c,v) in enumerate(zip(row["correct"],vals)):
        ax.text(i,v+.035,f'{c}/{row["total"]}',ha="center",va="bottom",fontsize=10)
axes[0].set_ylabel("Fraction answered correctly")
fig.tight_layout(w_pad=2)
art={"id":"dd-memory-reader-controls","kind":"figure","sha256_by_format":{}}
for ext in ["pdf","svg","png"]:
    dst=out/("dd-memory-reader-controls."+ext);fig.savefig(dst,bbox_inches="tight",dpi=180)
    art[ext]=str(dst);art["sha256_by_format"][ext]=hashlib.sha256(dst.read_bytes()).hexdigest()
result={"schema_version":"dd.completion-figures/1","status":"COMPLETE","artifacts":[art],"memory_tex_path":str(Path(art["pdf"]).relative_to(root/"manuscript"/"working-draft")),"counts":data,"limitations":["Replot of archived counts, not a new reader trial.","Temporal sample has nine cases; no uncertainty or causal advantage is inferred from these bars.","No conceptual-diagram dependency is consumed."]}
Path(a.result).write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({"memory_counts":data["overall"]}))
