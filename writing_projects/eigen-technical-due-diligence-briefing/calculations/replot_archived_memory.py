#!/usr/bin/env python3
"""Presentation-only replot of four archived exact-coordinate timing cells."""
import argparse, csv, hashlib, json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

parser=argparse.ArgumentParser()
parser.add_argument("--mode",required=True)
parser.add_argument("--args-json",required=True)
parser.add_argument("--result",required=True)
a=parser.parse_args()
assert a.mode=="smoke" and json.loads(a.args_json)=={}
root=Path.cwd()
result=Path(a.result)
out=result.with_suffix("").with_name(result.stem+"-memory-plots")
out.mkdir(parents=True,exist_ok=False)
hashof=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs=[]; rows=[]; samples={}
for q in (1,32,256,1024):
    p=root/f"evidence-snapshots/memory/parity-d19-r4-prefix-q{q}.json"
    c=json.loads(p.read_text())
    assert (c["N"],c["d"],c["fixed_coordinates"],c["location"],c["Q"])==(262144,19,4,"prefix",q)
    assert all(c["validation"].values())
    inputs.append({"path":str(p.relative_to(root)),"sha256":hashof(p)})
    row={"Q":q}
    for method in ("raw_packed_direct","weighted_unique_direct","recursive_exact_integer"):
        m=c["methods"][method]
        assert m["samples"]==11 and m["warmups"]==2
        row[method]=m["api_s_median"]*1e6
        samples[q,method]=np.asarray(m["api_s_samples"])*1e6
    rows.append(row)
csvpath=out/"archived-parity-timings.csv"
with csvpath.open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,"axes.spines.right":False,"pdf.fonttype":42,"svg.fonttype":"none"})
fig,axs=plt.subplots(1,2,figsize=(10.6,4.4),gridspec_kw={"width_ratios":[1,1.3]})
ax=axs[0]; ax.axis("off")
ax.text(0,1,"A  Keep the relation, not every prefix",transform=ax.transAxes,weight="bold",va="top",fontsize=12)
ax.text(.01,.85,"Three-bit even-parity worlds",transform=ax.transAxes,weight="bold")
for j,t in enumerate(("0  0  0","0  1  1","1  0  1","1  1  0")):
    ax.text(.1,.73-j*.10,t,transform=ax.transAxes,fontfamily="DejaVu Sans Mono",fontsize=15,color="#164b77")
ax.text(.5,.66,"Each pair looks\nindependent.\nTogether, the first\ntwo fix the third.",transform=ax.transAxes,va="center",linespacing=1.5)
ax.text(.02,.23,"A prefix needs only its running parity:\neven or odd. Reading a 1 switches state.\nOnly an even final state is accepted.",transform=ax.transAxes,linespacing=1.6)
ax.text(.02,.02,"Mathematical illustration of the retained rule",transform=ax.transAxes,fontsize=9,color="#555555")
ax=axs[1]
labels={"raw_packed_direct":"Packed direct scan","weighted_unique_direct":"Weighted unique scan","recursive_exact_integer":"Exact continuation"}
colors={"raw_packed_direct":"#c47d22","weighted_unique_direct":"#164b77","recursive_exact_integer":"#168b7c"}
for method in labels:
    x=[r["Q"] for r in rows]; y=[r[method] for r in rows]
    ax.plot(x,y,"o-",label=labels[method],color=colors[method],linewidth=2)
    for q in x:
        ax.scatter(np.full(11,q),samples[q,method],s=8,color=colors[method],alpha=.35)
ax.set_xscale("log",base=2); ax.set_yscale("log")
ax.set_xticks([1,32,256,1024],["1","32","256","1,024"])
ax.set_xlabel("Queries per batch")
ax.set_ylabel("Warm full-API time per batch ($\\mu$s)")
ax.set_title("B  Archived exact-coordinate measurements",loc="left",weight="bold",fontsize=12,pad=12)
ax.grid(alpha=.18,which="both")
ax.legend(frameon=False,fontsize=9,loc="upper left")
fig.text(.54,.015,"262,144 unique worlds; 19 bits; four fixed prefix coordinates.\nDots: 11 timed samples. Lines: medians, not scaling fits.",fontsize=9,va="bottom")
fig.subplots_adjust(bottom=.22,wspace=.26,top=.88,left=.035,right=.985)
artifacts=[]
for ext in ("pdf","svg","png"):
    p=out/f"archived-memory-parity.{ext}"
    fig.savefig(p,dpi=200,bbox_inches="tight")
    artifacts.append({"id":f"archived-memory-parity-{ext}","kind":"figure","path":str(p),"sha256":hashof(p)})
plt.close(fig)
result.write_text(json.dumps({"schema":"dd.presentation-only-replot/1","status":"COMPLETE","inputs":inputs,"artifacts":artifacts,"data":{"path":str(csvpath),"sha256":hashof(csvpath)},"summary":{"raw_api_us_Q1024":rows[-1]["raw_packed_direct"],"recursive_api_us_Q1024":rows[-1]["recursive_exact_integer"],"raw_over_recursive_Q1024":rows[-1]["raw_packed_direct"]/rows[-1]["recursive_exact_integer"]},"limitations":["Archived synthetic Boolean-query measurements, not a new benchmark or natural-language retrieval result.","Four fixed prefix coordinates at d19 only. No selection across coordinate locations or dimensions.","Warm API times exclude build, query preparation and process-first compilation. Eleven samples from one run are not independent campaign replicates.","Archive reports refusal for high-width controls and weighted scan wins on duplicate-heavy controls. The displayed structured law is not universal."]},indent=2)+"\n")
