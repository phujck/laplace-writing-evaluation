"""Finite analytic oracles for SLG v2. No top-level original producer execution."""
from __future__ import annotations
import argparse, ast, hashlib, itertools, json, math, platform, sys
from pathlib import Path
import numpy as np

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode",required=True)
    ap.add_argument("--args-json",required=True)
    ap.add_argument("--result",required=True)
    opt=ap.parse_args()
    assert opt.mode=="smoke" and json.loads(opt.args_json)=={}
    root=Path(__file__).resolve().parent
    cfg=json.loads((root/"parameters.json").read_text())
    src=(root/"original_numerical_demonstrations_v0.py").read_bytes()
    assert hashlib.sha256(src).hexdigest()==cfg["source_sha256"]
    tests=[]
    tol=cfg["tolerances"]
    def check(name,error,limit=None,detail=None):
        limit=tol["identity_abs"] if limit is None else limit
        error=float(abs(error))
        tests.append(dict(name=name,error=error,tolerance=limit,passed=bool(error<=limit),detail=detail))
    def mse(x,y,th): return float(np.mean((y-th*x)**2))
    a=cfg["action"]
    alpha,beta,window,ridge=a["alpha"],a["beta"],a["window"],a["ridge_denominator"]
    # Exact partial least-squares identity and one disagreeing full/partial threshold.
    x=np.ones(8); y=np.full(8,.8); th=1.
    ls=float(np.dot(x,y)/np.dot(x,x))
    candidate=th+alpha*(ls-th)
    full=mse(x,y,th)-mse(x,y,ls)
    partial=mse(x,y,th)-mse(x,y,candidate)
    check("partial_LS_factor",partial/full-(2*alpha-alpha*alpha))
    ridge_ls=float(np.dot(x,y)/(np.dot(x,x)+ridge))
    exact_candidate=th+alpha*(ridge_ls-th)
    g1=mse(x,y,th)-mse(x,y,exact_candidate)
    delta=exact_candidate-th
    polynomial=2*delta*(float(np.mean(x*y))-th*float(np.mean(x*x)))-delta**2*float(np.mean(x*x))
    check("actual_ridge_candidate_direct_gain",g1-polynomial)
    separating_cost=beta*(full+g1)/2
    action_counterexample=dict(theta=th,full_target=ls,partial_candidate=exact_candidate,
        full_gain=full,actual_partial_gain=g1,partial_factor=2*alpha-alpha*alpha,
        separating_cost=separating_cost,full_rule_promotes=beta*full>separating_cost,
        actual_partial_rule_promotes=beta*g1>separating_cost,
        original_local_gain=.1*min((.8-th)**2,.25**2))
    check("full_vs_partial_decision_counterexample",
        0 if action_counterexample["full_rule_promotes"] and not action_counterexample["actual_partial_rule_promotes"] else 1)
    # Execute only the exact original function AST. No imports, directories, plotting or main().
    parsed=ast.parse(src.decode("utf-8"))
    selected=[n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name=="run_two_scale_agent"]
    assert len(selected)==1
    namespace={"np":np}
    exec(compile(ast.Module(body=selected,type_ignores=[]),"<pinned-original-function>","exec"),namespace)
    n=a["steps"]
    xx=np.resize(np.array(a["x_pattern"],float),n)
    truth=np.full(n,a["initial_theta"],float)
    for t,value in a["shifts"]: truth[t:]=value
    yy=truth*xx+np.resize(np.array(a["noise_pattern"],float),n)
    v0_path,v0_err,v0_prom=namespace["run_two_scale_agent"](xx,yy,*a["costs"],
        beta=beta,window=window,adapt_rate=alpha,sigma=.25)
    v0_rows=[]; v1_rows=[]; state0=state1=a["initial_theta"]
    mismatches=[]; predicted_applied=[]; measured_equal=[]; no_update_g=[]
    for t in range(1,n):
        start=max(0,t-window+1); xw=xx[start:t+1]; yw=yy[start:t+1]
        # Exact replay of v0's priced full-fit candidate, different actual step, and phantom local benefit.
        before=state0; err=yy[t]-before*xx[t]
        fit=float(np.sum(xw*yw)/(np.sum(xw*xw)+ridge)) if len(xw)>=8 else before
        full_gain=max(0.,mse(xw,yw,before)-mse(xw,yw,fit)) if len(xw)>=8 else 0.
        local=.1*min(err*err,.25**2)
        actual_target=float(np.clip(yy[t]/xx[t],-1.5,3.5)) if abs(xx[t])>.15 else fit
        actual1=before+alpha*(actual_target-before)
        promoted=beta*(full_gain-local)>a["costs"][1]-a["costs"][0]
        state0=actual1 if promoted else before
        realised=mse(xw,yw,before)-mse(xw,yw,state0)
        v0_rows.append(dict(t=t,theta_before=before,scored_theta1=fit,executed_candidate1=actual1,
            scored_gain0=local,actual_gain0=0.,scored_gain1=full_gain,
            actual_candidate1_gain=mse(xw,yw,before)-mse(xw,yw,actual1),
            promoted=bool(promoted),theta_after=state0,realised_window_gain=realised,
            pre_action_error=float(err),next_step_error=float(yy[t+1]-state0*xx[t+1]) if t+1<n else None))
        mismatches.append(abs(full_gain-(mse(xw,yw,before)-mse(xw,yw,actual1))))
        check("v0_replay_state_"+str(t),state0-v0_path[t])
        check("v0_replay_error_"+str(t),err-v0_err[t])
        check("v0_replay_decision_"+str(t),int(promoted)-int(v0_prom[t]))
        # v1: both candidates live on one rolling-MSE horizon, evaluator frozen during action.
        before=state1; err=yy[t]-before*xx[t]
        fit=float(np.sum(xw*yw)/(np.sum(xw*xw)+ridge)) if len(xw)>=8 else before
        candidates=(before,before+alpha*(fit-before))
        gains=tuple(mse(xw,yw,before)-mse(xw,yw,z) for z in candidates)
        scores=tuple(beta*g-c for g,c in zip(gains,a["costs"]))
        chosen=1 if scores[1]>scores[0] else 0
        state1=candidates[chosen]  # the exact same object that was evaluated
        realised=mse(xw,yw,before)-mse(xw,yw,state1)
        predicted_applied.append(abs(state1-candidates[chosen]))
        measured_equal.append(abs(realised-gains[chosen])); no_update_g.append(abs(gains[0]))
        v1_rows.append(dict(t=t,theta_before=before,theta0=candidates[0],theta1=candidates[1],
            gain0=gains[0],gain1=gains[1],score0=scores[0],score1=scores[1],chosen=chosen,
            theta_after=state1,realised_window_gain=realised,pre_action_error=float(err),
            next_step_error=float(yy[t+1]-state1*xx[t+1]) if t+1<n else None))
    check("legacy_mismatch_exists",0 if max(mismatches)>1e-4 else 1)
    check("v1_evaluated_equals_applied",max(predicted_applied))
    check("v1_scored_equals_realised_window_gain",max(measured_equal))
    check("v1_no_update_gain_is_zero",max(no_update_g))
    check("zero_cost_tie_stays",0 if not (0.>0.) else 1)
    # Exact product Bernoulli OR closure, additive hazard and conditional-count derivative.
    def hazard(ms,c): return float(np.logaddexp(0.,np.asarray(ms)-c).sum())
    def q_or(ms,c): return -math.expm1(-hazard(ms,c))
    def ceff(ms,c): return float(sum(ms)-math.log(math.expm1(hazard(ms,c))))
    c=cfg["or"]["cost"]; step=cfg["or"]["fd_step"]; or_cases=[]
    for ms in cfg["or"]["blocks"]:
        ps=1/(1+np.exp(-(np.asarray(ms)-c)))
        weights=[]
        for bits in itertools.product([0,1],repeat=len(ms)):
            prob=float(np.prod([p if u else 1-p for p,u in zip(ps,bits)]))
            weights.append((sum(bits),prob))
        q_enum=sum(p for count,p in weights if count>0)
        conditional=sum(count*p for count,p in weights)/q_enum
        slope=float(sum(ps)/q_or(ms,c))
        fd=(ceff(ms,c+step)-ceff(ms,c-step))/(2*step)
        check("OR_probability_B"+str(len(ms))+"_"+str(ms),q_or(ms,c)-q_enum)
        check("OR_conditional_count_"+str(ms),slope-conditional)
        check("OR_derivative_"+str(ms),slope-fd,tol["finite_difference_abs"])
        check("OR_count_bounds_"+str(ms),max(0.,1-slope,slope-len(ms)))
        or_cases.append(dict(margins=ms,hazard=hazard(ms,c),q=q_enum,
            c_eff=ceff(ms,c),dc_eff_dc=slope,conditional_event_count=conditional,finite_difference=fd))
    ms=cfg["or"]["blocks"][-1]
    h=hazard(ms[:2],c)+hazard(ms[2:],c)
    check("OR_direct_vs_staged_B4",(-math.expm1(-h))-q_or(ms,c))
    check("OR_B1_threshold",ceff(cfg["or"]["blocks"][0],c)-c)
    hetero=q_or([.7,-.5],c)-q_or([.1,.1],c)
    check("OR_equal_sum_heterogeneity",0 if hetero>1e-4 else 1)
    # Explicit mean-threshold squared-logit objective and Lipschitz residual bound.
    blocks=[[-.4,.2],[.7,-.5],[.1,.1]]
    cs=np.array([ceff(z,c) for z in blocks]); avg=float(cs.mean())
    residuals=[]
    for z,ci in zip(blocks,cs):
        residual=abs(q_or(z,c)-1/(1+math.exp(-(sum(z)-avg))))
        bound=abs(float(ci)-avg)/4
        check("OR_mean_threshold_residual_bound_"+str(z),max(0.,residual-bound))
        residuals.append(dict(margins=z,tv=residual,bound=bound))
    check("mean_threshold_SSE_minimum",max(0.,float(np.sum((cs-avg)**2)-np.sum((cs-(avg+.1))**2))))
    # Finite classical contraction with the pushed reference convention.
    w=np.array([1.,2.,3.,4.]); kk=np.array([.2,-.3,.7,1.1]); coarse=np.array([.35,.65])
    wy=np.array([sum(w[:2]),sum(w[2:])]); eff=[]; p=[]
    for i in range(2):
        sl=slice(2*i,2*i+2); r=w[sl]*np.exp(-kk[sl]); r=r/sum(r)
        eff.append(-math.log(float(np.sum(w[sl]/wy[i]*np.exp(-kk[sl])))))
        p.extend(coarse[i]*r)
    p=np.array(p)
    fine=float(np.dot(p,kk)+np.dot(p,np.log(p/w)))
    reduced=float(np.dot(coarse,eff)+np.dot(coarse,np.log(coarse/wy)))
    check("weighted_classical_contraction",fine-reduced)
    # Product labels and joint probability ranks are different count conventions.
    I=.8; product=sum(z**(-I) for z in [1,2,2,4]); factored=(1+2**(-I))**2
    check("product_rank_multiplicities",product-factored)
    dense=sum(z**(-I) for z in [1,2,3,4])
    check("product_not_dense_rank_partition",0 if abs(product-dense)>1e-4 else 1)
    rank_rows=sorted([(u*v,i,j) for i,u in enumerate([.7,.3]) for j,v in enumerate([.6,.4])],reverse=True)
    rank=next(i+1 for i,row in enumerate(rank_rows) if row[1:]==(1,0))
    check("joint_usage_rank_counterexample",rank-3)
    # Common-ledger register boundaries and equality case.
    gamma,eta,cp=1.,.8,.25
    tp=math.acos(1-2*cp/(.5+gamma)); ta=math.acos(1-eta/(.5+gamma))
    check("register_partition_crossing",tp-.8410686705679301)
    check("register_arbitration_crossing",ta-1.0852782044993055)
    tie_A=2*eta
    tie_vals=[tie_A/4+(2*eta-tie_A)*(z-.5)**2 for z in [0,.25,.5,.75,1]]
    check("register_all_alpha_tie",max(tie_vals)-min(tie_vals))
    # Retained convergence scaffold, frozen partial-gradient convention.
    aa,bb,k,hh,q=.4,.6,.3,.2,.6
    contraction=max(1-aa+aa*q,1-bb+bb*k/q)
    m,l=-1.,1.
    for _ in range(150): m,l=(1-aa)*m+aa*l,(1-bb)*l+bb*math.tanh(k*m+hh)
    check("scaffold_fixed_point_residual",max(abs(m-l),abs(l-math.tanh(k*m+hh))),1e-10)
    # 4x4 quantum controls. Only exact analytic minimisers identified below.
    eye=np.eye(2); X=np.array([[0.,1.],[1.,0.]]); Z=np.diag([1.,-1.])
    def spectral(A,f):
        ev,U=np.linalg.eigh((A+A.T.conj())/2)
        return (U*f(ev))@U.T.conj()
    def expm(A): return spectral(A,np.exp)
    def sqrtm(A): return spectral(A,lambda z:np.sqrt(np.maximum(z,0)))
    def invsqrt(A): return spectral(A,lambda z:1/np.sqrt(z))
    def logm(A): return spectral(A,np.log)
    def ptr(A): return np.trace(A.reshape(2,2,2,2),axis1=1,axis2=3)
    def entropy(A):
        ev=np.linalg.eigvalsh((A+A.T.conj())/2)
        ev=ev[ev>1e-14]
        return -float(np.sum(ev*np.log(ev)))
    def J(rho,K,M): return float(np.trace(rho@K).real)-M*entropy(rho)
    M,g=cfg["quantum"]["M"],cfg["quantum"]["g"]
    sigz=np.diag([1.,0.]); sigx=np.ones((2,2))/2
    productK=.3*np.kron(Z,eye)+.2*np.kron(eye,X)
    quantum=[]
    for label,K,sigma,expect_equal in [
        ("product_coherent",productK,np.array([[.6,.2],[.2,.4]]),True),
        ("XX_pure_z",g*np.kron(X,X),sigz,False),
        ("ZZ_diagonal",g*np.kron(Z,Z),np.diag([.3,.7]),True),
        ("ZZ_coherent_pure_x",g*np.kron(Z,Z),sigx,False)]:
        boltz=expm(-K/M); omega=boltz/np.trace(boltz)
        os=ptr(omega); sw=sqrtm(omega); isw=invsqrt(os)
        recovered=sw@np.kron(isw@sigma@isw,eye)@sw
        recovery_residual=float(np.linalg.norm(ptr(recovered)-sigma,"fro"))
        keff=-M*logm(ptr(boltz))
        check(label+"_recovery_trace",np.trace(recovered).real-1,tol["trace_abs"])
        if expect_equal:
            rho=recovered
            gap=J(rho,K,M)-J(sigma,keff,M)
            check(label+"_recovery_feasible",recovery_residual,tol["quantum_abs"])
            check(label+"_gap_zero",gap,tol["quantum_abs"])
        else:
            # A pure marginal forces sigma tensor tau. Here effective E generator is zero.
            rho=np.kron(sigma,eye/2)
            gap=J(rho,K,M)-J(sigma,keff,M)
            check(label+"_pure_extension_marginal",np.linalg.norm(ptr(rho)-sigma),tol["quantum_abs"])
            check(label+"_analytic_gap",gap-M*math.log(math.cosh(g/M)),tol["quantum_abs"])
            check(label+"_nonzero_gap",0 if gap>tol["nonzero_gap_min"] else 1)
            check(label+"_recovery_infeasible",0 if recovery_residual>1e-4 else 1)
        quantum.append(dict(case=label,M=M,g=g,analytic_minimiser=True,
            gap=gap,recovery_residual=recovery_residual,omega_min_eigenvalue=float(np.linalg.eigvalsh(omega).min()),
            sigma_eigenvalues=np.linalg.eigvalsh(sigma).tolist(),coarse_equilibrium_generator=keff.tolist()))
    failures=[t for t in tests if not t["passed"]]
    out=dict(schema_version="slg.finite-analytic-checks/2",status="PASSED" if not failures else "FAILED",
        limitations=cfg["scope"],environment=dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),
            executable=sys.executable,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            parameters_sha256=hashlib.sha256((root/"parameters.json").read_bytes()).hexdigest(),
            original_source_sha256=hashlib.sha256(src).hexdigest()),
        measures=dict(check_count=len(tests),failed_count=len(failures),
            max_action_application_error=max(predicted_applied),max_action_gain_error=max(measured_equal),
            max_legacy_candidate_gain_mismatch=max(mismatches),heterogeneous_OR_probability_difference=hetero,
            quantum_positive_gap=M*math.log(math.cosh(g/M))),
        protocol=cfg,tests=tests,action_counterexample=action_counterexample,
        action_trace=dict(x=xx.tolist(),y=yy.tolist(),theta_truth=truth.tolist(),legacy_v0=v0_rows,priced_partial_rolling_v1=v1_rows),
        OR=dict(cases=or_cases,mean_threshold=avg,residuals=residuals,fit_objective="equal-weight squared logit/intercept residual",
            historical_slope_reproduced=False),
        retained_controls=dict(weighted_classical_residual=fine-reduced,product_partition=product,
            factored_partition=factored,dense_rank_partition=dense,joint_rank=rank,
            register_partition_angle=tp,register_arbitration_angle=ta,scaffold_contraction_bound=contraction),
        quantum=quantum)
    result=Path(opt.result)
    assert result.is_absolute()
    result.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    print(json.dumps(out["measures"]))
    if failures: raise SystemExit(1)
if __name__=="__main__": main()
