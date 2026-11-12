"""Replot archived quantum records. No eigensolver, circuit simulation or new benchmark."""
import argparse,csv,hashlib,json,platform
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument("--mode",required=True);p.add_argument("--args-json",required=True);p.add_argument("--result",required=True);a=p.parse_args()
assert a.mode=="smoke" and json.loads(a.args_json)=={}
root=Path.cwd()
paths={"projection":root/"evidence-snapshots/quantum/operator_projection_result.json",
"metric":root/"evidence-snapshots/quantum/metric_pool_sweep.csv"}
pins={"projection":"3023e8f5b138983e7d8400cf08bab033b01fa7351465f010fe1731b4fa350754",
"metric":"531c3778144cae2c73f43f8ff8e2f8035190e47d55989cd30cdf1400ebb1f323"}
for k,f in paths.items():assert hashlib.sha256(f.read_bytes()).hexdigest()==pins[k]
d=json.loads(paths["projection"].read_text())
with paths["metric"].open() as f:rows=list(csv.DictReader(f))
out=Path(a.result).parent/(Path(a.result).stem+"-plots");out.mkdir()
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"axes.spines.top":False,"axes.spines.right":False,"pdf.fonttype":42,"svg.fonttype":"none"})
blue="#247BA0";teal="#168A78";amber="#BD6A21"
artifacts=[]
def save(fig,name):
 for ext in ("pdf","svg","png"):
  f=out/(name+"."+ext);fig.savefig(f,bbox_inches="tight",dpi=180)
  artifacts.append({"id":name+"-"+ext,"path":str(f),"kind":"figure","sha256":hashlib.sha256(f.read_bytes()).hexdigest()})
 plt.close(fig)
fig,(ax,bx)=plt.subplots(1,2,figsize=(8.3,3.3))
for key,col,mark in [("local",blue,"o"),("global",amber,"s")]:
 pts=d["identity2"]["per_observable"][key]["points"]
 ns=[q["n"] for q in pts]
 ax.semilogy(ns,[q["var_grad_scalar"] for q in pts],marker=mark,color=col,lw=1.6,label=key.capitalize()+" observable")
 bx.plot(ns,[q["op_grad_fraction_mean"] for q in pts],marker=mark,color=col,lw=1.6,label=key.capitalize()+" observable")
ax.set(xlabel="Qubits",ylabel="Scalar gradient variance",title="A. The scalar signal shrinks")
bx.set(xlabel="Qubits",ylabel="Normalised operator-gradient norm squared",ylim=(0,.62),title="B. Operator content remains")
bx.axhline(.5,ls=":",color="0.6",lw=1)
ax.legend(frameon=False,fontsize=8);bx.legend(frameon=False,fontsize=8)
fig.tight_layout(w_pad=2);save(fig,"archived-operator-projection")
fig,(ax,bx)=plt.subplots(1,2,figsize=(8.3,3.5),gridspec_kw={"width_ratios":[1,1.3]})
ax.bar([0,1],[.8,.9],color=[teal,amber],width=.55)
ax.set(xticks=[0,1],xticklabels=["Low-gap\nchannel","High-gap\nchannel"],ylabel="Raw residual overlap",ylim=(0,1.15),title="A. Louder is not more useful")
ax.text(0,.88,"gap 1.79",ha="center",fontsize=9);ax.text(1,.98,"gap 30.05",ha="center",fontsize=9)
raw=[q for q in rows if q["method"]=="raw"];gap=[q for q in rows if q["method"]=="gap_metric"]
assert len(raw)==len(gap)==5
xs=[float(q["scale"]) for q in raw]
bx.plot(xs,[float(q["bare_error"]) for q in raw],"--",color="0.5",label="Before enlargement",lw=1.3)
bx.plot(xs,[float(q["error"]) for q in raw],"-s",color=amber,label="Largest raw overlap",lw=1.8)
bx.plot(xs,[float(q["error"]) for q in gap],"-o",color=teal,label="Gap-aware selection",lw=1.8)
bx.set(xlabel=r"Coupling $\lambda$ (model units)",ylabel="Ground-energy error (model units)",title="B. One added direction, different gains",ylim=(0,.5))
bx.legend(frameon=False,fontsize=8)
fig.tight_layout(w_pad=2);save(fig,"archived-gap-aware-selection")
result={"schema_version":"dd.archived-replot/1","interpretation":"Presentation-only replot of archived classical simulations, not rerun or independent validation.",
"inputs":[{"path":str(paths[k].relative_to(root)),"sha256":pins[k]} for k in paths],
"archival_provenance_limits":"Original scripts/configuration preserved in evidence-snapshots/quantum and packet01. No historical supervised run manifest supplied.",
"environment":{"python":platform.python_version(),"matplotlib":matplotlib.__version__},
"artifacts":artifacts,"checks":{"expected_metric_rows":len(rows),"metric_couplings":xs,
"projection_qubits":[q["n"] for q in d["identity2"]["per_observable"]["local"]["points"]]}}
Path(a.result).write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result["checks"]))
