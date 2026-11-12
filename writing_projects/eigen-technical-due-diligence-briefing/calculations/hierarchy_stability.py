"""Source-defined Gaussian hierarchy: deterministic stability illustration, not a new empirical experiment.
Phases v4 Appendices B,C, source hashes b5c6486d3fa24057ed6c70fb396295230d2af0d8dd4b4ddba8faf58d903fe1b5 and
5728939928f428200e951c41f9796778b1f2549cd72819756dfb476cc2a21f91.
"""
import argparse,json,math,hashlib,csv
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
out=root/"manuscript"/"working-draft"/"figures"/("hierarchy-"+Path(a.result).stem)
out.mkdir(parents=True,exist_ok=False)
b,s,beta,alpha=1.2,.4,.6,.35
c=math.sqrt(2/math.pi);r=math.exp(-1)
def kc(r): return 2*(1+r)/((1+r)*b-(1-r)*s)
def mat(r,K): return np.array([[r,(1-r)*s],[K*r,1-K*(b-(1-r)*s)]])
def nc(r,L): return math.pi/2*(kc(r)/(alpha*beta))**2*(math.pi/2)**(L-1)
errors=[];mismatch=0;tested=0
for rr in [.1,r,.8]:
    errors.append(min(abs(np.linalg.eigvals(mat(rr,kc(rr)))+1)))
    for L in [1,2,3]:
        for N in np.geomspace(16,1024,41):
            for al in np.linspace(.02,.85,53):
                K=al*beta*math.sqrt(2*N/math.pi)*c**(L-1)
                rho=max(abs(np.linalg.eigvals(mat(rr,K))))
                mismatch+=int((rho<1)!=(0<K<kc(rr)));tested+=1
assert mismatch==0 and max(errors)<1e-12
thresholds=[nc(r,L) for L in [1,2,3]]
plt.rcParams.update({"font.family":"DejaVu Serif","font.size":9,"mathtext.fontset":"dejavuserif","pdf.fonttype":42,"svg.fonttype":"none","axes.spines.top":False,"axes.spines.right":False})
fig,axes=plt.subplots(1,2,figsize=(7.2,3.4))
colors=["#0072B2","#D55E00","#009E73"];styles=["-","--",":"]
N=np.geomspace(16,1024,401)
bounds=[kc(r)/(beta*np.sqrt(2*N/math.pi)*c**(L-1)) for L in [1,2,3]]
ax=axes[0]
ax.fill_between(N,0,bounds[0],color=colors[0],alpha=.14)
for j in [1,2]: ax.fill_between(N,bounds[j-1],bounds[j],color=colors[j],alpha=.13)
for j in range(3): ax.plot(N,bounds[j],color=colors[j],ls=styles[j],lw=1.6,label=r"$L="+str(j+1)+"$")
ax.axhline(alpha,color="#555555",ls="-.",lw=.9)
for j,nn in enumerate(thresholds):
    ax.plot(nn,alpha,"o",ms=3.5,color=colors[j])
    ax.annotate(str(round(nn)),(nn,alpha),xytext=(0,-14),textcoords="offset points",ha="center",fontsize=8)
ax.text(21,.12,"Stable even without\nadditional layers",fontsize=8,color="#005680")
ax.text(270,.68,"Unstable for all\nthree depths",fontsize=8,color="#555555")
ax.text(17,.365,r"$\alpha=0.35$",fontsize=8)
ax.set(xscale="log",xlim=(16,1024),ylim=(0,.8),xlabel=r"Population $N$",ylabel=r"Update size $\alpha$")
ax.set_xticks([16,64,256,1024],["16","64","256","1024"])
ax.set_title("(a) Hierarchy moves the stability boundary",loc="left",fontsize=9)
ax.legend(frameon=False,ncol=3,loc="upper right",fontsize=8,handlelength=1.8)
ax=axes[1];h=np.linspace(.1,3,401)
for j in range(3): ax.plot(h,nc(np.exp(-h),j+1),color=colors[j],ls=styles[j],lw=1.6,label=r"$L="+str(j+1)+"$")
ax.axvline(1,color="#999999",ls=":",lw=.8)
for j,n in enumerate(thresholds): ax.plot(1,n,"o",ms=3.5,color=colors[j])
ax.text(1.55,65,"Stable below each\ncorresponding curve",fontsize=8,color="#005680")
ax.set(xlim=(.1,3),ylim=(0,550),xlabel=r"Update interval $h/\tau_r$",ylabel=r"Critical population $N_c^{(L)}$")
ax.set_title("(b) Slower updates also allow larger groups",loc="left",fontsize=9)
ax.legend(frameon=False,loc="upper left",fontsize=8)
fig.tight_layout(w_pad=1.5)
artifact={"id":"dd-hierarchy-stability","kind":"figure","category":"mathematical","sha256_by_format":{}}
for ext in ["pdf","svg","png"]:
    dst=out/("dd-hierarchy-stability."+ext);fig.savefig(dst,bbox_inches="tight",dpi=180)
    artifact[ext]=str(dst);artifact["sha256_by_format"][ext]=hashlib.sha256(dst.read_bytes()).hexdigest()
data=out/"phase-boundaries.csv"
with data.open("w",newline="") as f:
    w=csv.writer(f);w.writerow(["N","alpha_c_L1","alpha_c_L2","alpha_c_L3"]);w.writerows(zip(N,*bounds))
result={"schema_version":"dd.hierarchy-stability/1","status":"complete","parameters":{"alpha":alpha,"beta":beta,"b":b,"s":s,"h_over_tau":1,"c":c},"N_c_L1":thresholds[0],"N_c_L2":thresholds[1],"N_c_L3":thresholds[2],"jacobians_checked":tested,"classification_mismatches":mismatch,"max_boundary_eigenvalue_error":float(max(errors)),"artifacts":[artifact],"data":{"path":str(data),"sha256":hashlib.sha256(data.read_bytes()).hexdigest()},"tex_path":str(Path(artifact["pdf"]).relative_to(root/"manuscript"/"working-draft")),"limitations":["Exact linear stability of the specified deterministic sampled map using its iterated Gaussian expected-majority response.","Not exact finite-block majority combinatorics, realised noisy verdict dynamics, a nonlinear bifurcation proof, general hierarchy advantage or ANF's distinct two-derivative protocol.","Continuous population interpolation. No empirical or independent scientific verification."]}
Path(a.result).write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({k:v for k,v in result.items() if k not in ["artifacts","data"]}))
