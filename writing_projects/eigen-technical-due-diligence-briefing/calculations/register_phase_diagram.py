"""Deterministic register-choice phase diagram, not a measured phase transition."""
import argparse, json, math, csv, hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
p=argparse.ArgumentParser()
p.add_argument("--mode",required=True)
p.add_argument("--args-json",required=True)
p.add_argument("--result",required=True)
a=p.parse_args()
assert a.mode=="smoke" and json.loads(a.args_json)=={}
root=Path.cwd()
out=root/"manuscript"/"working-draft"/"figures"/("phase-"+Path(a.result).stem)
out.mkdir(parents=True,exist_ok=False)
gamma,eta,c_slice=1.,.8,.25
theta=np.linspace(0,math.pi,1001)
balanced=(.5+gamma)*(1-np.cos(theta))/2
boundary=np.minimum(balanced,eta/2)
theta_att=math.acos(1-eta/(.5+gamma))
theta_split=math.acos(1-2*c_slice/(.5+gamma))
alphas=np.linspace(0,1,2001)
errors=[]
for th in np.linspace(0,math.pi,101):
    A=(.5+gamma)*2*(1-math.cos(th))
    direct=A*alphas*(1-alphas)+2*eta*(alphas-.5)**2
    errors.append(abs(float(direct.min())-min(A/4,eta/2)))
checks={"max_alpha_grid_error":max(errors),
"slice_crossing_error":abs((.5+gamma)*(1-math.cos(theta_split))/2-c_slice),
"meeting_point_error":abs((.5+gamma)*(1-math.cos(theta_att))/2-eta/2),
"balanced_at_theta_half":float(alphas[np.argmin((.5+gamma)*2*(1-math.cos(.5))*alphas*(1-alphas)+2*eta*(alphas-.5)**2)])==.5,
"suppressed_at_theta_two":int(np.argmin((.5+gamma)*2*(1-math.cos(2))*alphas*(1-alphas)+2*eta*(alphas-.5)**2)) in (0,len(alphas)-1)}
assert checks["max_alpha_grid_error"]<1e-12 and checks["slice_crossing_error"]<1e-12 and checks["meeting_point_error"]<1e-12
assert checks["balanced_at_theta_half"] and checks["suppressed_at_theta_two"]
plt.rcParams.update({"font.family":"DejaVu Serif","font.size":10,"mathtext.fontset":"dejavuserif","pdf.fonttype":42,"svg.fonttype":"none","axes.spines.top":False,"axes.spines.right":False})
fig,ax=plt.subplots(figsize=(6.4,4.1))
ax.fill_between(theta,0,boundary,color="#009E73",alpha=.22)
left=theta<=theta_att
ax.fill_between(theta,boundary,.65,where=left,color="#0072B2",alpha=.18,interpolate=True)
ax.fill_between(theta,boundary,.65,where=~left,color="#E69F00",alpha=.20,interpolate=True)
ax.plot(theta,boundary,color="#203340",lw=1.8)
ax.plot([theta_att,theta_att],[eta/2,.65],color="#203340",lw=1.4)
ax.axhline(c_slice,color="#666666",lw=1,ls="--")
ax.plot(theta_split,c_slice,"o",color="#203340",ms=5)
ax.plot(theta_att,eta/2,"o",color="#203340",ms=4)
ax.text(.37,.52,"Balanced sharing\n"+r"$\alpha=1/2$",ha="center",va="center",fontsize=10,color="#005680")
ax.text(2.13,.52,"Shared register,\none evaluator suppressed\n"+r"$\alpha=0$ or $1$",ha="center",va="center",fontsize=10,color="#7A4F00")
ax.text(2.13,.12,"Separate registers\nboth tasks retained",ha="center",va="center",fontsize=11,color="#00664C")
ax.annotate(r"$C_{\rm part}=0.25$ slice",xy=(2.75,.25),xytext=(2.48,.29),ha="center",fontsize=9,color="#555555")
ax.annotate(r"$\theta_{\rm split}\simeq0.841$",xy=(theta_split,c_slice),xytext=(.17,.14),fontsize=9,arrowprops={"arrowstyle":"->","lw":.8})
ax.annotate(r"$(\theta_{\rm att},\eta/2)$",xy=(theta_att,eta/2),xytext=(1.32,.35),fontsize=9,arrowprops={"arrowstyle":"->","lw":.8})
ax.set(xlim=(0,math.pi),ylim=(0,.65),xlabel=r"Task disagreement $\theta$ (rad)",ylabel=r"Additional register price $C_{\rm part}$")
ax.set_xticks([0,.5,1,1.5,2,2.5,math.pi],["0","0.5","1","1.5","2","2.5",r"$\pi$"])
fig.tight_layout()
artifact={"id":"dd-register-phase-diagram","kind":"figure","category":"mathematical","sha256_by_format":{}}
for ext in ["pdf","svg","png"]:
    dst=out/("dd-register-phase-diagram."+ext)
    fig.savefig(dst,bbox_inches="tight",dpi=180)
    artifact[ext]=str(dst)
    artifact["sha256_by_format"][ext]=hashlib.sha256(dst.read_bytes()).hexdigest()
csvpath=out/"register-boundary.csv"
with csvpath.open("w",newline="") as f:
    w=csv.writer(f);w.writerow(["theta","balanced_cost","C_crit"]);w.writerows(zip(theta,balanced,boundary))
result={"schema_version":"dd.register-phase-diagram/1","status":"complete","parameters":{"gamma":gamma,"eta":eta,"C_part_slice":c_slice},"theta_split":theta_split,"theta_attention":theta_att,"checks":checks,"artifacts":[artifact],"data":{"path":str(csvpath),"sha256":hashlib.sha256(csvpath.read_bytes()).hexdigest()},"tex_path":str(Path(artifact["pdf"]).relative_to(root/"manuscript"/"working-draft")),"limitations":["Deterministic optimisation phase diagram of the declared finite model.","No physical thermodynamic transition, measured training advantage or independent proof is asserted."]}
Path(a.result).write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(checks))
