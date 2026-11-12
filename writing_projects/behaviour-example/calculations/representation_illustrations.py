"""DD mathematical illustrations, not measured performance or independent proof."""
import argparse, csv, hashlib, json, math, platform
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
p=argparse.ArgumentParser()
p.add_argument("--mode", choices=["smoke","full"], required=True)
p.add_argument("--args-json", required=True)
p.add_argument("--result", required=True)
a=p.parse_args()
assert json.loads(a.args_json)=={}
root=Path.cwd()
out=Path(a.result).parent / (Path(a.result).stem+"-illustrations")
out.mkdir(parents=True,exist_ok=False)
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,
"axes.spines.right":False,"axes.labelcolor":"#203340","text.color":"#203340",
"pdf.fonttype":42,"svg.fonttype":"none"})
blue="#247BA0"; teal="#168A78"; amber="#BD6A21"
files=[]
def savefig(fig,name):
    for ext in ("pdf","svg","png"):
        path=out/(name+"."+ext)
        fig.savefig(path,bbox_inches="tight",dpi=180)
        files.append({"id":name+"-"+ext,"path":str(path),"kind":"figure",
                      "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    plt.close(fig)
def savecsv(name,header,rows):
    path=out/(name+".csv")
    with path.open("w",newline="") as f:
        w=csv.writer(f);w.writerow(header);w.writerows(rows)
    files.append({"id":name+"-data","path":str(path),"kind":"data",
                  "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
# Shared-register model, same objective for fixed and revisable partition.
gamma=1.;eta=.8;cost=.25
theta=[math.pi*i/400 for i in range(401)]
balanced=[2*(1-math.cos(x))*(.5+gamma)/4 for x in theta]
fixed=[min(v,eta/2) for v in balanced]
adaptive=[min(v,cost) for v in fixed]
cross=math.acos(1-2*cost/(.5+gamma))
suppress=math.acos(1-eta/(.5+gamma))
fig,(ax,bx)=plt.subplots(1,2,figsize=(9,3.5),gridspec_kw={"width_ratios":[1,1.4]})
angle=1.2; av=(1,0);bv=(math.cos(angle),math.sin(angle));q=tuple((x+y)/2 for x,y in zip(av,bv))
ax.plot([av[0],bv[0]],[av[1],bv[1]],color="0.65",lw=1.5)
ax.scatter(*av,color=blue,s=55);ax.scatter(*bv,color=teal,s=55);ax.scatter(*q,color=amber,s=55)
ax.annotate("Task 1 minimum $a$",av,xytext=(-55,-25),textcoords="offset points",color=blue)
ax.annotate("Task 2 minimum $b$",bv,xytext=(-5,12),textcoords="offset points",color=teal)
ax.annotate("Shared register $q_* $",q,xytext=(5,10),textcoords="offset points",color=amber)
ax.set_aspect("equal");ax.set_xlim(-.1,1.3);ax.set_ylim(-.25,1.2);ax.set_axis_off()
ax.set_title("A. Sharing creates a compromise",loc="left",fontsize=11)
bx.plot(theta,fixed,color=blue,lw=2,label="Fixed shared register")
bx.plot(theta,adaptive,color=teal,lw=2.6,label="Partition allowed")
bx.axhline(cost,color=amber,ls=":",lw=1.3,label="Price of separation")
bx.axvline(cross,color=teal,ls="--",lw=1)
bx.axvline(suppress,color="0.6",ls="--",lw=1)
bx.annotate("Separate registers\nbecome cheaper",xy=(cross,cost),xytext=(1.35,.13),
arrowprops={"arrowstyle":"->","color":teal},color=teal)
bx.set(xlabel=r"Disagreement angle $\theta$ (radians)",ylabel="Optimal priced loss",
xlim=(0,math.pi),ylim=(0,.45))
bx.set_title("B. Change the representation before sacrificing a task",loc="left",fontsize=10)
bx.legend(frameon=False,loc="lower right",fontsize=8)
fig.tight_layout(w_pad=2)
savefig(fig,"shared-register-price")
savecsv("shared-register-price",["theta_rad","balanced_loss","fixed_optimum","partition_optimum"],
zip(theta,balanced,fixed,adaptive))
# Exact four-state illustration. Column generator, uniform stationary distribution.
G=[[-5,4,1,0],[4,-7,0,3],[1,0,-5,4],[0,3,4,-7]]
Y=[1,1,-1,-1];Z=[1,-1,-1,1]
YG=[sum(Y[i]*G[i][j] for i in range(4)) for j in range(4)]
ZG=[sum(Z[i]*G[i][j] for i in range(4)) for j in range(4)]
assert YG==[-4*Y[j]+2*Z[j] for j in range(4)]
assert ZG==[2*Y[j]-12*Z[j] for j in range(4)]
assert all(sum(G[i][j] for i in range(4))==0 for j in range(4))
r=math.sqrt(20.)
def yz(t,z0):
    c=math.cosh(r*t);s=math.sinh(r*t);e=math.exp(-8*t)
    return e*(c+(4+2*z0)*s/r),e*(z0*c+(2-4*z0)*s/r)
ts=[1.5*i/300 for i in range(301)]
curves=[[.5*(1+yz(t,z)[0]) for t in ts] for z in (1,-1)]
coarse=[.5*(1+math.exp(-4*t)) for t in ts]
fig,ax=plt.subplots(figsize=(6.4,3.7))
for curve,color,label in zip(curves,[blue,teal],["Fine process: start in state 1","Fine process: start in state 2"]):
    ax.plot(ts,curve,lw=2,color=color,label=label)
ax.plot(ts,coarse,lw=1.7,ls="--",color=amber,label="Coarse model without imbalance")
ax.set(xlabel="Time (rate units)",ylabel="Probability in region A",ylim=(.48,1.02),xlim=(0,1.5))
ax.legend(frameon=False,fontsize=9)
fig.tight_layout()
savefig(fig,"retention-trajectories")
savecsv("retention-trajectories",["time","start_state_1","start_state_2","coarse_without_memory"],
zip(ts,*curves,coarse))
# Analytic formulae, not sampled quantum measurements.
ns=list(range(1,31))
vg=[(1/8)*(3/8)**(n-1) for n in ns]
vl=[1/(8*n*n) for n in ns]
fig,ax=plt.subplots(figsize=(6.4,3.7))
ax.semilogy(ns,vg,color=blue,lw=2,label="Global product cost")
ax.semilogy(ns,vl,color=teal,lw=2,label="Mean local cost")
ax.set(xlabel="Number of qubits $n$",ylabel="Variance of one gradient component",xlim=(1,30))
ax.legend(frameon=False)
fig.tight_layout()
savefig(fig,"global-local-feedback")
savecsv("global-local-feedback",["n","global_variance","local_variance"],zip(ns,vg,vl))
checks={"generator_columns_sum_to_zero":True,"two_coordinate_closure_exact_integer_check":True,
"shared_crossing":cross,"attention_suppression_boundary":suppress,
"same_coarse_initial_mass":curves[0][0]==curves[1][0]==1.,
"initial_mass_derivatives":[-.5*2,-.5*6],
"limiting_stationary_mass":.5}
result={"schema_version":"dd.mathematical-illustrations/1","status":"computed",
"interpretation":"Deterministic mathematical illustrations of stated models, not empirical performance, independent verification, or a broad theorem proof.",
"checks":checks,"parameters":{"gamma":gamma,"eta":eta,"partition_cost":cost,"generator":G,
"retained_observables":{"y":Y,"z":Z},"time_end":1.5,"time_intervals":300},
"source_basis":["reading/shared-register-and-prx-interpretation-20261015.md",
"development/proposed-argument-reader-and-visual-plan-20261015.md",
"reading/primary-foundations-passage-interpretation-20261015.md"],
"environment":{"python":platform.python_version(),"matplotlib":matplotlib.__version__},
"artifacts":files}
Path(a.result).write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({"output_directory":str(out),"artifacts":len(files),"checks":checks}))
