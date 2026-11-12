import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
import argparse,json,hashlib,time
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

parser=argparse.ArgumentParser()
parser.add_argument('--mode',required=True)
parser.add_argument('--args-json',required=True)
parser.add_argument('--result',required=True)
a=parser.parse_args()
assert a.mode=='full' and json.loads(a.args_json)=={}
cfgpath=Path(__file__).with_suffix('.json')
c=json.loads(cfgpath.read_text())
started=time.monotonic()
sx=np.array([[0.,1.],[1.,0.]])
sy=np.array([[0.,-1j],[1j,0.]])
sz=np.diag([1.,-1.])
I=np.eye(2)

def spectrum(g,n):
    b=np.diag(np.sqrt(np.arange(1,n)),1)
    H=c['omega_q']/2*np.kron(sz,np.eye(n))+c['omega_b']*np.kron(I,np.diag(np.arange(n)))+g*np.kron(sx,b+b.T)
    E,V=np.linalg.eigh(H)
    return E,V.reshape(2,n,2*n)

def reduced(E,V,beta=None):
    if beta is None:
        psi=V[:,:,0]
        return psi@psi.conj().T
    weights=np.exp(-beta*(E-E[0]));weights/=weights.sum()
    return np.einsum('ink,jnk,k->ij',V,V.conj(),weights)

def radius(rho):
    return float(np.linalg.norm([np.trace(rho@s).real for s in (sx,sy,sz)]))

def logratio(rho):
    p=np.linalg.eigvalsh(rho)
    assert p[0]>0
    return float(np.log(p[1]/p[0]))

betas=np.geomspace(.4,30.,65)
curves=[];cutoff=[]
for g in c['couplings']:
    E,V=spectrum(g,c['cutoff'])
    E2,V2=spectrum(g,c['check_cutoff'])
    ground=reduced(E,V);ground2=reduced(E2,V2)
    cutoff.append({'g':g,'energy_difference':float(abs(E[0]-E2[0])),'state_frobenius_difference':float(np.linalg.norm(ground-ground2))})
    rows=[]
    for beta in betas:
        rho=reduced(E,V,float(beta))
        rows.append({'beta':float(beta),'radius':radius(rho),'hmf_gap':logratio(rho)/float(beta),'beta_hmf_gap':logratio(rho),'distance_to_ground':float(np.linalg.norm(rho-ground))})
    curves.append({'g':g,'ground_energy':float(E[0]),'ground_rho':ground.real.tolist(),'ground_radius':radius(ground),'ground_log_ratio':logratio(ground),'validation_beta':c['validation_beta'],'validation_distance_to_ground':float(np.linalg.norm(reduced(E,V,c['validation_beta'])-ground)),'rows':rows})
D=c['omega_q']+c['omega_b']
weak=[]
for g in np.geomspace(.001,.1,15):
    E,V=spectrum(float(g),c['cutoff']);q=float(reduced(E,V)[0,0].real)
    weak.append({'g':float(g),'excited_probability':q,'probability_over_g_squared':q/g**2,'prediction':1/D**2})
joint=[]
for kappa in [.5,1.,2.]:
    rows=[]
    for beta in [8.,10.,12.,16.,20.]:
        g=kappa*D*np.exp(-beta*c['omega_q']/2)
        E,V=spectrum(float(g),c['cutoff']);q=float(reduced(E,V,beta)[0,0].real)
        target=1+kappa*kappa
        rows.append({'beta':beta,'g':float(g),'excited_probability':q,'q_over_thermal':float(q*np.exp(beta*c['omega_q'])),'prediction':target,'relative_error':float(abs(q*np.exp(beta*c['omega_q'])/target-1))})
    joint.append({'kappa':kappa,'rows':rows})
# Exact qubit thermal-congruence/Lorentz identity, independently evaluated as matrices.
rng=np.random.default_rng(271828);lorentz=[]
for eta in [-2.,-.7,0.,.7,2.]:
    vec=rng.normal(size=3);vec=.6*vec/np.linalg.norm(vec)
    rho=(I+sum(vec[i]*s for i,s in enumerate((sx,sy,sz))))/2
    A=np.diag(np.exp(np.array([-eta/2,eta/2])))
    raw=A@rho@A.conj().T
    x0=np.cosh(eta)-vec[2]*np.sinh(eta)
    z=vec[2]*np.cosh(eta)-np.sinh(eta)
    expected=(x0*I+vec[0]*sx+vec[1]*sy+z*sz)/2
    lorentz.append({'eta':eta,'matrix_error':float(np.linalg.norm(raw-expected)),'determinant_error':float(abs(np.linalg.det(raw)-np.linalg.det(rho))),'normalized_trace_error':float(abs(np.trace(raw/x0)-1))})
checks={'cutoff_state':max(x['state_frobenius_difference'] for x in cutoff)<1e-10,'cutoff_energy':max(x['energy_difference'] for x in cutoff)<1e-9,'low_temperature_ground_state':max(x['validation_distance_to_ground'] for x in curves)<1e-8,'weak_dressing_coefficient':abs(weak[0]['probability_over_g_squared']*D**2-1)<1e-4,'joint_limit_at_beta20':max(x['rows'][-1]['relative_error'] for x in joint)<1e-4,'lorentz_matrix_identity':max(x['matrix_error'] for x in lorentz)<1e-12,'lorentz_determinant':max(x['determinant_error'] for x in lorentz)<1e-12}
checks={key:bool(value) for key,value in checks.items()}
plt.rcParams.update({'font.family':'serif','mathtext.fontset':'stix','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'xtick.direction':'in','ytick.direction':'in','svg.fonttype':'none'})
fig,axes=plt.subplots(2,2,figsize=(7.0,5.4),constrained_layout=True)
colors=['#0072B2','#D55E00','#009E73']
for item,col in zip(curves,colors):
    label=rf'$g/\omega_q={item["g"]:g}$'
    axes[0,0].plot(betas,[r['radius'] for r in item['rows']],color=col,label=label)
    axes[0,0].axhline(item['ground_radius'],color=col,ls=':',lw=.8)
    axes[0,1].plot(betas,[r['beta_hmf_gap'] for r in item['rows']],color=col)
    axes[0,1].axhline(item['ground_log_ratio'],color=col,ls=':',lw=.8)
axes[0,0].plot(betas,np.tanh(betas*c['omega_q']/2),color='black',ls='--',lw=1,label=r'$g=0$')
axes[0,0].set(xlabel=r'$\beta\omega_q$',ylabel=r'$r_Q$');axes[0,0].legend(fontsize=8)
axes[0,1].set(xlabel=r'$\beta\omega_q$',ylabel=r'$\beta\Delta_{\mathrm{MF}}$')
axes[1,0].plot([x['g']**2 for x in weak],[x['probability_over_g_squared']*D**2-1 for x in weak],color=colors[0])
axes[1,0].axhline(0.,color='black',ls='--',lw=1)
axes[1,0].set(xlabel=r'$g^2/\omega_q^2$',ylabel=r'$(\omega_q+\omega_b)^2p_\uparrow/g^2-1$')
for item,col in zip(joint,colors):
    axes[1,1].plot([r['beta'] for r in item['rows']],[r['q_over_thermal'] for r in item['rows']],color=col,marker='o',ms=3,label=rf'$\kappa={item["kappa"]:g}$')
    axes[1,1].axhline(1+item['kappa']**2,color=col,ls=':',lw=.8)
axes[1,1].set(xlabel=r'$\beta\omega_q$',ylabel=r'$p_\uparrow e^{\beta\omega_q}$');axes[1,1].legend(fontsize=8)
for ax,label in zip(axes.flat,['(a)','(b)','(c)','(d)']):ax.text(.02,1.03,label,transform=ax.transAxes,va='bottom')
result=Path(a.result);out=result.parent/(result.stem+'-figures');out.mkdir(parents=True,exist_ok=True)
svg=out/'hmf-zero-temperature-and-joint-path.svg';png=out/'hmf-zero-temperature-and-joint-path.png'
fig.savefig(svg);fig.savefig(png,dpi=180);plt.close(fig)
caption='Single-oscillator spin-boson control, H=omega_q sigma_z/2+omega_b b†b+g sigma_x(b+b†), omega_b/omega_q=1.7. (a) Physical reduced-spin Bloch radius approaches the traced ground-state radius (dotted), which remains below one at nonzero coupling. (b) The dimensionless mean-force gap beta Delta_MF approaches the ground-state log eigenvalue ratio (dotted), so Delta_MF itself vanishes as temperature while retaining a mixed reduced ground state. (c) Relative deviation of the excited-spin weight from g²/(omega_q+omega_b)² approaches zero (dashed). (d) Along g(beta)=kappa(omega_q+omega_b) exp(-beta omega_q/2), the scaled excited weight approaches1+kappa² (dotted). Displayed thermal curves reach beta30; the independent beta80 endpoint checks ground-state convergence. Independent diagonalization at two oscillator cutoffs checks truncation for this finite-bath control; no continuum or generic exact spin-boson solution is claimed.'
record={'schema':'hmf-root-zero-temperature-control/1','configuration':c,'configuration_sha256':hashlib.sha256(cfgpath.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'curves':curves,'cutoff_checks':cutoff,'weak_dressing':weak,'joint_paths':joint,'lorentz_identity_checks':lorentz,'checks':checks,'all_checks':all(checks.values()),'artifacts':[{'id':'hmf-zero-temperature-joint-path','svg':str(svg),'png':str(png),'caption':caption}],'elapsed_seconds':time.monotonic()-started,'limitations':['Single harmonic mode at finite, converged oscillator cutoff; not the continuum bath.','Weak-coupling and matched low-temperature expressions are asymptotic, not a generic all-coupling solution.','Lorentz identity is a known matrix correspondence checked here in the thermal filter; it does not establish gravitational field equations.']}
result.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'all_checks':record['all_checks'],'checks':checks,'result':str(result),'elapsed_seconds':record['elapsed_seconds']}))
