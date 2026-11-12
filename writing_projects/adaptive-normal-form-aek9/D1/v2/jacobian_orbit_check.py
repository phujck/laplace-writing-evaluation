"""D1 v2 finite source-pinned Jacobian/orbit checks. Author-run, not independent review.
No trajectories, hierarchy sweeps, models, network, source writes or installs.
"""
import argparse, hashlib, json, math, sys
from pathlib import Path
import numpy as np

SNAPSHOT_SHA = "3ae1cfd976172d13521121be5b1338649d117bc503a36a1dcb624ec927e39682"
def eigs(A):
    return [{"real": float(z.real), "imag": float(z.imag), "modulus": float(abs(z))}
            for z in np.linalg.eigvals(A)]
def bisect_nonzero(fn, lo, hi):
    original = [float(lo), float(hi)]
    fl, fh = fn(lo), fn(hi)
    if not (fl > 0 and fh < 0):
        raise ValueError(f"Nonzero root not bracketed: {lo,hi,fl,fh}")
    first_signs = [float(fl), float(fh)]
    iterations = 0
    for iterations in range(1, 101):
        mid = (lo+hi)/2.0
        fm = fn(mid)
        if fm > 0:
            lo=mid
        elif fm < 0:
            hi=mid
        else:
            lo=hi=mid
            break
        if hi-lo <= 2e-16:
            break
    root=(lo+hi)/2.0
    return root, {"initial_bracket":original,"initial_values":first_signs,
                  "final_bracket":[float(lo),float(hi)],
                  "final_values":[float(fn(lo)),float(fn(hi))],
                  "root_equation_residual":float(fn(root)), "iterations":iterations}
def jac_fd(fn, state, eps):
    z=np.asarray(state,dtype=float)
    return np.column_stack([(fn(z+eps*np.eye(2)[j])-fn(z-eps*np.eye(2)[j]))/(2*eps)
                            for j in range(2)])
def inspect_pair(fn,jac,positive,steps):
    positive=np.asarray(positive,dtype=float)
    negative=-positive
    JP,JM=jac(positive),jac(negative)
    # Actual matrix product, no old eig2 helper and no assumption JP=JM in execution.
    product=JM@JP
    diffs=[]
    for label,state,J in [("positive",positive,JP),("negative",negative,JM)]:
        for eps in steps:
            fd=jac_fd(fn,state,eps)
            diffs.append({"state":label,"step":eps,"centred_difference":fd.tolist(),
                          "max_abs_error":float(np.max(np.abs(fd-J)))})
    return {"state_order":None,"positive_state":positive.tolist(),
            "negative_state":negative.tolist(),"image_positive":fn(positive).tolist(),
            "image_negative":fn(negative).tolist(),
            "positive_to_negative_residual":float(np.max(np.abs(fn(positive)-negative))),
            "negative_to_positive_residual":float(np.max(np.abs(fn(negative)-positive))),
            "jacobian_positive":JP.tolist(),"jacobian_negative":JM.tolist(),
            "jacobian_symmetry_error":float(np.max(np.abs(JP-JM))),
            "one_step_positive_eigenvalues":eigs(JP),"one_step_negative_eigenvalues":eigs(JM),
            "two_step_jacobian_direct":product.tolist(),"two_step_eigenvalues":eigs(product),
            "finite_differences":diffs}

def main(result_path):
    raw=Path("D1/v2/source-inputs.json").read_bytes()
    sha=hashlib.sha256(raw).hexdigest()
    if sha != SNAPSHOT_SHA:
        raise ValueError("Source-input snapshot pin changed")
    cfg=json.loads(raw)
    # Only exact selected original O_mean/g_func definitions, pinned locally.
    ns={k:getattr(math,k) for k in ("erf","sqrt","pi","exp","sinh","cosh")}
    ns["__builtins__"]={}
    exec(compile(cfg["snippets"][0]["text"],"<pinned-R1-definitions>","exec"),ns)
    f0,g0=ns["O_mean"],ns["g_func"]
    ap=cfg["parameters"]["anf"]
    N,r,alpha,beta=ap["N"],ap["r"],ap["alpha"],ap["beta"]
    f=lambda t:f0(t,N,beta)
    g=lambda t:g0(t,N,beta)
    def gg(t):
        u=math.sqrt(N/2)*math.sinh(beta*t)
        up=math.sqrt(N/2)*beta*math.cosh(beta*t)
        upp=math.sqrt(N/2)*beta**2*math.sinh(beta*t)
        return 2/math.sqrt(math.pi)*math.exp(-u*u)*(upp-2*u*up*up)
    def anf_map(state):
        m,t=state
        e=m-f(t)
        return np.array([r*m+(1-r)*f(t),t+alpha*g(t)*e])
    def anf_jac(state):
        m,t=state
        e=m-f(t)
        return np.array([[r,(1-r)*g(t)],
                         [alpha*g(t),1+alpha*gg(t)*e-alpha*g(t)**2]])
    theta,bracket=bisect_nonzero(lambda t:alpha*g(t)*f(t)-(1+r)*t,
                                *ap["theta_bracket"])
    m=-(1-r)/(1+r)*f(theta)
    anf=inspect_pair(anf_map,anf_jac,[m,theta],cfg["parameters"]["difference_steps"])
    anf.update({"state_order":["m","theta"],"parameters":ap,"root_theta":theta,
                "root_bracket":bracket,"mismatch":m-f(theta),
                "pJ_at_1":float(np.linalg.det(np.eye(2)-anf_jac([m,theta]))),
                "pJ_at_1_analytic":-alpha*(1-r)*gg(theta)*(m-f(theta)),
                "K_at_zero":alpha*g(0)**2,
                "Nc":math.pi*(1+r)/(2*alpha*beta**2),
                "N0":math.pi*r/(2*alpha*beta**2)})
    pp=cfg["parameters"]["ph"]
    b,s,alpha,beta=pp["b"],pp["s"],pp["alpha"],pp["beta"]
    r=math.exp(-1)
    cplant=(1-r)*s
    D=b-cplant/(1+r)
    Kc=2/D
    Nc=math.pi*Kc*Kc/(2*alpha**2*beta**2)
    cases=[]
    for ratio in pp["size_ratios"]:
        N=ratio*Nc
        a=beta*math.sqrt(N/2)
        R=lambda u:math.erf(a*u)
        Rp=lambda u:2*a/math.sqrt(math.pi)*math.exp(-(a*u)**2)
        def ph_map(state):
            x,t=state
            xn=r*x+cplant*t
            return np.array([xn,t+alpha*R(xn-b*t)])
        def ph_jac(state):
            x,t=state
            u=r*x+cplant*t-b*t
            k=alpha*Rp(u)
            return np.array([[r,cplant],[k*r,1-k*(b-cplant)]])
        z,bracket=bisect_nonzero(lambda z:alpha*R(z)-Kc*z,1e-9,alpha*D/2)
        Theta=z/D
        X=-cplant/(1+r)*Theta
        pair=inspect_pair(ph_map,ph_jac,[X,Theta],cfg["parameters"]["difference_steps"])
        k=alpha*Rp(z)
        tr=1+r-k*(b-cplant)
        det=r*(1-k*b)
        pair.update({"state_order":["x","theta"],"size_ratio":ratio,"N":N,
                     "a":a,"z_mismatch_magnitude":z,"Theta":Theta,"X":X,
                     "root_bracket":bracket,"k":k,"k_over_Kc":k/Kc,
                     "K_origin":alpha*Rp(0),
                     "mismatch_at_positive_state":r*X+cplant*Theta-b*Theta,
                     "cycle_equation_z_rhs":alpha*D*R(z)/2,
                     "jury":{"1_minus_trace_plus_det":1-tr+det,
                             "1_plus_trace_plus_det":1+tr+det,"1_minus_det":1-det}})
        cases.append(pair)
    allpairs=[anf]+cases
    maxres=max(max(p["positive_to_negative_residual"],p["negative_to_positive_residual"])
               for p in allpairs)
    maxfd=max(v["max_abs_error"] for p in allpairs for v in p["finite_differences"])
    phmod=max(e["modulus"] for p in cases for key in
              ("one_step_positive_eigenvalues","one_step_negative_eigenvalues","two_step_eigenvalues")
              for e in p[key])
    af=sorted([e["real"] for e in anf["two_step_eigenvalues"]],reverse=True)
    tests={
        "snapshot_pin":sha==SNAPSHOT_SHA,
        "orbit_residuals_below_1e-10":maxres<cfg["oracles"]["residual_max"],
        "analytic_vs_fd_max_below_declared_tolerance":maxfd<cfg["oracles"]["finite_difference_max_abs_error"],
        "anf_oracle_intervals":all(lo<v<hi for v,(lo,hi) in zip(af,cfg["oracles"]["anf_two_step_real_intervals"])),
        "anf_saddle":af[0]>1 and 0<af[1]<1,
        "ph_all_local_moduli_below_one":phmod<1,
        "ph_all_0_lt_k_lt_Kc":all(0<c["k_over_Kc"]<1 for c in cases),
        "ph_all_Jury_positive":all(v>0 for c in cases for v in c["jury"].values())
    }
    out={"schema":"anf.D1-local-results/2","work_id":cfg["work"],
         "source_snapshot_sha256":sha,"runtime":{"python":sys.version,"numpy":np.__version__,
         "eigensolver":"numpy.linalg.eigvals, direct J_negative @ J_positive"},
         "anf":anf,"ph":{"parameters":pp,"r":r,"D":D,"Kc":Kc,"Nc":Nc,"cases":cases},
         "anf_max_map_residual":max(anf["positive_to_negative_residual"],anf["negative_to_positive_residual"]),
         "ph_max_map_residual":max(max(p["positive_to_negative_residual"],p["negative_to_positive_residual"]) for p in cases),
         "max_jacobian_fd_error":maxfd,"ph_max_local_modulus":phmod,
         "oracle_tests":tests,"all_declared_local_checks_pass":all(tests.values()),
         "scientific_status":"AUTHOR_RUN_FINITE_CHECKS_INDEPENDENT_SCIENCE_PENDING",
         "limitations":["Exactly four small-map orbit cases, no trajectory or global basin experiment.",
         "Erf responses are specified proxies, not exact finite-binomial agents.",
         "No formal proof checker or independent scientific judgement.",
         "No hierarchy, reconfiguration, forcing, stochastic or transformer checks."]}
    Path(result_path).write_text(json.dumps(out,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"all_declared_local_checks_pass":all(tests.values()),
                      "max_map_residual":maxres,"max_fd_error":maxfd,
                      "ph_max_local_modulus":phmod}))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--mode",required=True,choices=["smoke"])
    p.add_argument("--args-json",required=True)
    p.add_argument("--result",required=True)
    args=p.parse_args()
    if json.loads(args.args_json)!={}:raise ValueError("No arguments admitted")
    main(args.result)
