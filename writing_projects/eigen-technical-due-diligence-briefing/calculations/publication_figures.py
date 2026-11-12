"""Publication-size replot. Consumes fixed tables only, never reruns a scientific experiment."""
import argparse,csv,hashlib,json,math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
p=argparse.ArgumentParser()
for k in ("mode","args-json","result"):p.add_argument("--"+k,required=True)
a=p.parse_args();assert a.mode=="smoke" and json.loads(a.args_json)=={}
root=Path.cwd();out=Path(a.result).parent/(Path(a.result).stem+"-aps")
out.mkdir(exist_ok=False)
plt.rcParams.update({"font.family":"DejaVu Serif","mathtext.fontset":"dejavuserif","font.size":9,
"axes.labelsize":10,"legend.fontsize":8,"xtick.direction":"in","ytick.direction":"in",
"axes.spines.top":True,"axes.spines.right":True,"axes.linewidth":.7,
"lines.linewidth":1.5,"lines.markersize":4,"pdf.fonttype":42,"svg.fonttype":"none"})
blue="#0072B2";orange="#D55E00";green="#009E73"
inputs=[];outputs=[]
def read(path):
 f=root/path;inputs.append({"path":path,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()})
 return f.read_text()
def table(name):
 path="manuscript/research_runs/run-c3bb46b0151942ca.result-illustrations/"+name+".csv"
 rows=list(csv.DictReader(read(path).splitlines()))
 return {k:np.array([float(r[k]) for r in rows]) for k in rows[0]}
def save(fig,name,caption,category):
 fig.tight_layout(pad=.7)
 row={"id":name,"kind":"figure","caption":caption,"category":category,"sha256_by_format":{}}
 for ext in ("pdf","svg","png"):
  f=out/(name+"."+ext);fig.savefig(f,dpi=220)
  row[ext]=str(f)
  row["sha256_by_format"][ext]=hashlib.sha256(f.read_bytes()).hexdigest()
 outputs.append(row)
 plt.close(fig)
def panel(ax,label):
 ax.text(.97,.97,label,transform=ax.transAxes,va="top",ha="right",fontweight="bold")
d=table("shared-register-price")
fig,(ax,bx)=plt.subplots(1,2,figsize=(6.4,2.65),gridspec_kw={"width_ratios":[.8,1.25]})
theta=1.2;v=np.array([math.cos(theta),math.sin(theta)]);u=np.array([1.,0]);q=(u+v)/2
ax.plot([u[0],v[0]],[u[1],v[1]],color=".65",lw=1)
for z,c,label,delta in [(u,blue,"$a$",(4,-10)),(v,green,"$b$",(4,5)),(q,orange,"$q_*$",(5,2))]:
 ax.plot(*z,"o",color=c);ax.annotate(label,z,xytext=delta,textcoords="offset points",color=c)
ax.set(xlim=(-.05,1.35),ylim=(-.15,1.15));ax.set_aspect("equal");ax.axis("off");panel(ax,"(a)")
bx.plot(d["theta_rad"],d["fixed_optimum"],color=blue,label=r"$L_B^*$")
bx.plot(d["theta_rad"],d["partition_optimum"],color=green,ls="--",label=r"$L_C^*$")
bx.axhline(.25,color=orange,ls=":",label=r"$C_{\rm part}$")
bx.axvline(.8410686705679301,color=".6",ls=":",lw=.8)
bx.set(xlabel=r"$\theta$ (rad)",ylabel=r"$L^*$",xlim=(0,math.pi),ylim=(0,.45))
bx.legend(frameon=False,loc="lower right");panel(bx,"(b)")
save(fig,"dd-shared-register-aps",
"Mathematical illustration of the shared-register model. (a) Two tasks prefer a and b, while their equally weighted quadratic compromise is q*=(a+b)/2. (b) Optimised fixed-register loss L_B* and partition-enabled loss L_C* versus disagreement angle theta, with gamma=1, eta=0.8 and partition price C_part=0.25 in the source's dimensionless loss units. Separation becomes cheaper at theta=0.8411 rad, before the fixed-register optimum sacrifices a task at theta=1.0853 rad. The data are analytic model values from the retained illustration run, not measured performance.","mathematical")
d=table("retention-trajectories")
fig,ax=plt.subplots(figsize=(4.6,2.8))
for key,c,ls,label in [("start_state_1",blue,"-","Start in 1"),("start_state_2",green,"-","Start in 2"),("coarse_without_memory",orange,"--","Coarse, no memory")]:
 ax.plot(d["time"],d[key],color=c,ls=ls,label=label)
ax.set(xlabel=r"$t$ (inverse-rate units)",ylabel=r"$p_A(t)$",xlim=(0,1.5),ylim=(.48,1.02))
ax.legend(frameon=False)
save(fig,"dd-retention-trajectories-aps",
"Exact mathematical trajectories for the constructed four-state process. p_A(t) is probability in region A. Two initial microstates have p_A(0)=1 but different hidden imbalance z. The coarse model omitting z predicts one intermediate trajectory. Retaining z, or the exact memory kernel obtained by eliminating it, recovers both curves. Time is measured in units inverse to the base transition rate. No experimental data or fitted dynamics are used.","mathematical")
d=table("global-local-feedback")
fig,ax=plt.subplots(figsize=(4.6,2.8))
ax.semilogy(d["n"],d["global_variance"],color=blue,label=r"$C_G$")
ax.semilogy(d["n"],d["local_variance"],color=green,label=r"$C_L$")
ax.set(xlabel=r"$n$",ylabel=r"$\mathrm{Var}(\partial_j C)$",xlim=(1,30))
ax.legend(frameon=False)
save(fig,"dd-global-local-aps",
"Analytic gradient variances for the product-state example of Cerezo et al. C_G=1-product_j cos^2(theta_j/2) and C_L=1-(1/n)sum_j cos^2(theta_j/2) have the same zero-cost target. For independent uniform angles, Var(partial_j C_G)=(1/8)(3/8)^(n-1), whereas Var(partial_j C_L)=1/(8n^2). n is the number of qubits. These curves are exact values in that model, not hardware measurements or a general convergence guarantee.","mathematical")
d=json.loads(read("evidence-snapshots/quantum/operator_projection_result.json"))
fig,(ax,bx)=plt.subplots(1,2,figsize=(6.4,2.7))
for key,c,mark in [("local",blue,"o"),("global",orange,"s")]:
 pts=d["identity2"]["per_observable"][key]["points"];ns=np.array([r["n"] for r in pts])
 ax.semilogy(ns,[r["var_grad_scalar"] for r in pts],color=c,marker=mark,mfc="none",label=key.capitalize())
 bx.errorbar(ns,[r["op_grad_fraction_mean"] for r in pts],yerr=[r["op_grad_fraction_std"] for r in pts],color=c,marker=mark,mfc="none",capsize=2,label=key.capitalize())
ax.set(xlabel=r"$n$",ylabel=r"$\mathrm{Var}(g)$")
bx.set(xlabel=r"$n$",ylabel=r"$r_{\rm op}$",ylim=(0,.8))
bx.axhline(.5,color=".6",ls=":",lw=.8)
ax.legend(frameon=False);panel(ax,"(a)");panel(bx,"(b)")
save(fig,"dd-operator-projection-aps",
"Archived classical calculations from the operatorial-loss prototype, seed 20240603 and 2000 samples per point. (a) Variance of the scalar gradient g decreases with qubit number n. (b) The recorded normalised operator-gradient fraction r_op remains near one half. Error bars in (b) are the archived sample standard deviations, not standard errors or confidence intervals. Local and global observable ensembles nearly coincide in this particular experiment. The result contrasts projected scalar feedback with retained operator content. It does not demonstrate that this operator can be measured or optimised at no additional cost.","archived simulation")
rows=list(csv.DictReader(read("evidence-snapshots/quantum/metric_pool_sweep.csv").splitlines()))
fig,ax=plt.subplots(figsize=(4.6,2.8))
raw=[r for r in rows if r["method"]=="raw"];gap=[r for r in rows if r["method"]=="gap_metric"]
xs=[float(r["scale"]) for r in raw]
ax.plot(xs,[float(r["bare_error"]) for r in raw],color=".5",ls="--",label="Before enlargement")
ax.plot(xs,[float(r["error"]) for r in raw],color=orange,marker="s",label="Raw overlap")
ax.plot(xs,[float(r["error"]) for r in gap],color=green,marker="o",label="Gap-aware")
ax.set(xlabel=r"$\lambda$",ylabel=r"$E_{\mathcal{P}}-E_0$",ylim=(0,.5))
ax.legend(frameon=False)
save(fig,"dd-gap-selection-aps",
"Archived reduced-space comparison from the residual-method prototype. lambda scales the declared coupling and E_P-E_0 is the retained-space ground-energy error, both in the model's dimensionless units. Each method adds one direction from the same candidate pool. Selecting by raw residual amplitude chooses a high-gap channel, while the producer's amplitude-over-gap rule selects a more useful low-gap channel. The resulting finite-model error is substantially lower. This is not a hardware test or proof that every gap-aware enlargement converges.","archived simulation")
rows=[];samples={}
for q in (1,32,256,1024):
 c=json.loads(read(f"evidence-snapshots/memory/parity-d19-r4-prefix-q{q}.json"))
 r={"Q":q}
 for method in ("raw_packed_direct","weighted_unique_direct","recursive_exact_integer"):
  r[method]=c["methods"][method]["api_s_median"]*1e6
  samples[q,method]=np.array(c["methods"][method]["api_s_samples"])*1e6
 rows.append(r)
fig,(ax,bx)=plt.subplots(1,2,figsize=(6.4,2.8),gridspec_kw={"width_ratios":[.8,1.25]})
ax.axis("off");panel(ax,"(a)")
ax.text(.25,.84,r"$x_1\quad x_2\quad x_3$",transform=ax.transAxes)
for j,t in enumerate(("0    0    0","0    1    1","1    0    1","1    1    0")):
 ax.text(.25,.7-j*.12,t,fontfamily="DejaVu Sans Mono",transform=ax.transAxes)
ax.text(.15,.08,r"$x_1\oplus x_2\oplus x_3=0$",transform=ax.transAxes,color=blue)
for m,col,lab,marker in [("raw_packed_direct",orange,"Packed scan","s"),("weighted_unique_direct",blue,"Unique scan","^"),("recursive_exact_integer",green,"Continuation","o")]:
 x=[r["Q"] for r in rows];y=[r[m] for r in rows]
 bx.plot(x,y,color=col,marker=marker,label=lab)
 for q in x:bx.scatter(np.full(11,q),samples[q,m],s=5,color=col,alpha=.35)
bx.set_xscale("log",base=2);bx.set_yscale("log")
bx.set_xticks([1,32,256,1024],["1","32","256","1024"])
bx.set(xlabel=r"$Q$",ylabel=r"$t_{\rm API}$ ($\mu$s)")
bx.legend(frameon=False,loc="upper left");bx.text(.75,.97,"(b)",transform=bx.transAxes,va="top",ha="center",fontweight="bold")
save(fig,"dd-memory-parity-aps",
"Retaining a relation rather than its list of instances. (a) Mathematical three-bit even-parity example under a uniform source law. Every pair of bits is independent, but two bits jointly determine the third. A running parity state suffices to represent allowed continuations. (b) Archived measurements for the 19-bit law with 262144 unique worlds, queries fixing four prefix coordinates and batch size Q. t_API is warm full-API time per batch. Small dots are all eleven samples and lines connect medians, not fitted scaling laws. Build, query preparation and process-first compilation are excluded. The same campaign records refusal for high-width laws and direct-scan wins on a duplicate-heavy control.","mixed mathematical and archived measurement")
Path(a.result).write_text(json.dumps({"schema":"dd.aps-presentation/1","status":"COMPLETE","inputs":inputs,"artifacts":outputs,"scope":"Presentation-only from existing data. No scientific rerun.","style":{"profile":"profiles/visual_style.json","version":2,"font":"DejaVu Serif","size":9,"max_width_inches":6.4},"limitations":["Figure captions distinguish mathematical illustrations and archived measured or simulated results.","New error bars are archived sample standard deviations, not inferred uncertainty.","Main-manuscript placement and final printed-size inspection remain separate."]},indent=2)+"\n")
