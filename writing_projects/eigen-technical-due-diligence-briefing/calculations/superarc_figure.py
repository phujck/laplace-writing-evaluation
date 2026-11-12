"""Presentation-only figure from archived SuperARC report values."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
p=argparse.ArgumentParser()
for k in ("mode","args-json","result"):p.add_argument("--"+k,required=True)
a=p.parse_args();assert a.mode=="smoke" and json.loads(a.args_json)=={}
f=Path("evidence-snapshots/superarc/score-and-format-controls.json")
d=json.loads(f.read_text())
out=Path(a.result).parent/(Path(a.result).stem+"-figures");out.mkdir(exist_ok=False)
plt.rcParams.update({"font.family":"DejaVu Serif","mathtext.fontset":"dejavuserif","font.size":9,"axes.labelsize":10,"legend.fontsize":7.5,"xtick.direction":"in","ytick.direction":"in","lines.linewidth":1.5,"pdf.fonttype":42,"svg.fonttype":"none"})
fig,(ax,bx)=plt.subplots(1,2,figsize=(6.4,3.15),gridspec_kw={"width_ratios":[1,1.25]})
arms=["A1","A3","A2"];x=np.arange(3);bottom=np.zeros(3)
for j,label,color in [(0,"Non-print/non-ordinal","#009E73"),(1,"Ordinal","#0072B2"),(2,"Print-type","#D55E00")]:
 values=np.array([d["phi"][arm]["rho"][j] for arm in arms])
 ax.bar(x,values,bottom=bottom,width=.62,label=label,color=color)
 bottom+=values
assert np.allclose(bottom,1)
ax.set(xticks=x,xticklabels=["Bare","Execute/fix","Loop"],ylabel=r"$\rho_k$",ylim=(0,1.03))
ax.legend(frameon=False,loc="upper center",bbox_to_anchor=(.5,-.14))
ax.text(.02,1.04,"(a)",transform=ax.transAxes,fontweight="bold")
controls=d["controls"]["rows"]
for i,r in enumerate(controls):
 color="#0072B2" if i==0 else "#009E73"
 bx.plot(r["difference"],i,"o",color=color)
 if r["lo"] is not None:
  bx.hlines(i,r["lo"],r["hi"],color=color,lw=1.5)
  bx.vlines([r["lo"],r["hi"]],i-.07,i+.07,color=color,lw=1)
bx.axvline(0,color=".5",ls=":",lw=1)
bx.set(yticks=range(3),yticklabels=[r["basis"] for r in controls],xlabel=r"$\Delta\varphi=\varphi_{\rm loop}-\varphi_{\rm execute/fix}$",ylim=(2.5,-.5),xlim=(-.04,.10))
bx.text(.02,1.04,"(b)",transform=bx.transAxes,fontweight="bold")
fig.tight_layout(pad=.8,w_pad=1.1)
art={"id":"dd-superarc-controls","sha256_by_format":{}}
for ext in ("pdf","svg","png"):
 path=out/("dd-superarc-controls."+ext);fig.savefig(path,dpi=220)
 art[ext]=str(path);art["sha256_by_format"][ext]=hashlib.sha256(path.read_bytes()).hexdigest()
plt.close(fig)
result={"schema":"dd.archival-figure/1","status":"COMPLETE","input":{"path":str(f),"sha256":hashlib.sha256(f.read_bytes()).hexdigest()},"artifacts":[art],"caption":"Archived SuperARC campaign decomposition, N=100 twelve-term binary targets. (a) rho_k is the fraction in each correct-answer class. All three arms were recorded correct under the campaign's distinct correctness routes, but the bare arm is mostly in the penalised print-type class. (b) Delta phi compares loop and execute/fix arms. Removing commentary with the class assignments held fixed removes the positive separation. Horizontal intervals are the retained report's 95 percent paired-bootstrap bands at resample size100, seed20260804,100resamples. The re-binned point has no interval reported here. Scores concern formula text, while A2/A3 correctness used banked program execution. Prompt, search and format differences prevent these increments from isolating causal execution or recursion benefits. Replotted from archived report objects and the skeptic's explicitly transcribed control tables, not a new experiment.","limitations":d["limitations"]}
Path(a.result).write_text(json.dumps(result,indent=2)+"\n")
