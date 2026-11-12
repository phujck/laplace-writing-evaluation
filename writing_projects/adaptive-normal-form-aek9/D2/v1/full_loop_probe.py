"""Preregistered finite D2 trajectories. No D1 producer/reroot/Jacobian check rerun.
Outputs are isolated raw summary, full undecimated NPZ and fixed-rule CSV samples.
"""
import argparse,csv,hashlib,json,math,sys
from pathlib import Path
import numpy as np
PIN="fad267b935529433741ca167e299e4371c924c4c86a7db76489787cfdb94e1dd"
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def norm(v):return float(np.max(np.abs(v)))
def clean(v):
    if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
    if isinstance(v,list):return [clean(x) for x in v]
    if isinstance(v,(np.integer,np.floating)):v=v.item()
    if isinstance(v,float) and not math.isfinite(v):return None
    return v
def run(result_path):
    raw=Path("D2/v1/protocol-source-inputs.json").read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PIN:raise ValueError("Protocol pin changed")
    cfg=json.loads(raw)
    ns={k:getattr(math,k) for k in ("sqrt","erf","pi","sinh","cosh","exp")}
    ns["__builtins__"]={}
    exec(compile(cfg["snippets"][0]["text"],"<pinned-original-functions>","exec"),ns)
    f0,g0=ns["O_mean"],ns["g_func"]
    # Eigenvectors only seed NEW perturbation trajectories, from retained D1 J.
    ev,vec=np.linalg.eig(np.array(cfg["D1_reuse"]["anf"]["jacobian"],float))
    vectors={}
    for name,idx in [("unstable",int(np.argmax(np.abs(ev)))),("stable",int(np.argmin(np.abs(ev))))]:
        v=np.real(vec[:,idx]);v=v/np.linalg.norm(v)
        if v[1]<0:v=-v
        vectors[name]={"eigenvalue":float(np.real(ev[idx])),"unit_vector":v.tolist()}
    summaries=[];full={};csv_rows=[];total_updates=0
    for case in cfg["cases"]:
        H=case["horizon"];model=case["model"];ref=None
        if model=="ANF":
            N=case["N"];r=.3;alpha=.01;beta=.5
            f=lambda t:f0(t,N,beta);g=lambda t:g0(t,N,beta)
            if case["seed"] in ("source_plus","source_minus","theta_only"):
                initial=np.array(cfg["seed_definitions"][case["seed"]],float)
            else:
                ref=np.array(cfg["D1_reuse"]["anf"]["state"],float)
                initial=ref.copy()
                if "unstable_eigenvector" in case["seed"]:initial+=1e-7*np.array(vectors["unstable"]["unit_vector"])
                if "stable_eigenvector" in case["seed"]:initial+=1e-7*np.array(vectors["stable"]["unit_vector"])
            if N==900:ref=np.array(cfg["D1_reuse"]["anf"]["state"],float)
            def diag(z):
                m,t=z
                return m-f(t),alpha*g(t)**2
            def step(z,e):
                m,t=z
                return np.array([r*m+(1-r)*f(t),t+alpha*g(t)*e])
        else:
            p=cfg["D1_reuse"]["ph"];pc=p["cases"][case["D1_case_index"]]
            N=case["N"];r=p["r"];alpha=.35;beta=.6;b=1.2;s=.4;a=beta*math.sqrt(N/2)
            ref=np.array(pc["state"],float)
            initial=np.array([.1,.15],float) if case["seed"]=="source_generic" else ref+np.array([1e-4,0.])
            def diag(z):
                x,t=z;u=r*x+(1-r)*s*t-b*t
                return u,alpha*2*a/math.sqrt(math.pi)*math.exp(-(a*u)**2)
            def step(z,e):
                x,t=z
                return np.array([r*x+(1-r)*s*t,t+alpha*math.erf(a*e)])
        z=np.full((H+1,2),np.nan);ee=np.full(H+1,np.nan);KK=np.full(H+1,np.nan)
        z[0]=initial;last=0;error=None
        for k in range(H):
            try:
                ee[k],KK[k]=diag(z[k])
                if not np.all(np.isfinite([ee[k],KK[k]])):raise FloatingPointError("nonfinite diagnostic")
                nxt=step(z[k],ee[k])
                if not np.all(np.isfinite(nxt)):raise FloatingPointError("nonfinite next state")
                z[k+1]=nxt;last=k+1;total_updates+=1
            except (OverflowError,ValueError,FloatingPointError) as exc:
                error={"step":k,"type":type(exc).__name__,"message":str(exc),"last_finite_state":z[last].tolist()}
                break
        try:ee[last],KK[last]=diag(z[last])
        except (OverflowError,ValueError,FloatingPointError) as exc:
            if error is None:error={"step":last,"type":type(exc).__name__,"message":str(exc),"last_finite_state":z[last].tolist()}
        z=z[:last+1];ee=ee[:last+1];KK=KK[:last+1]
        p2=np.full(last+1,np.nan)
        if last>=2:p2[2:]=np.max(np.abs(z[2:]-z[:-2]),axis=1)
        anti=np.max(np.abs(z[1:]+z[:-1]),axis=1) if last>=1 else np.array([])
        dist=np.minimum(np.max(np.abs(z-ref),axis=1),np.max(np.abs(z+ref),axis=1)) if ref is not None else np.full(last+1,np.nan)
        def window(lo,hi):
            lo=max(0,lo);hi=min(hi,last);sl=ee[lo:hi+1];zs=z[lo:hi+1]
            if hi<lo or not np.all(np.isfinite(sl)):return {"start":lo,"end":hi,"available":False}
            idx=np.arange(lo,hi+1);even=sl[idx%2==0];odd=sl[idx%2==1]
            pv=p2[max(2,lo):hi+1];dv=dist[lo:hi+1]
            return {"start":lo,"end":hi,"available":True,"count":len(sl),"max_abs_e":float(np.max(np.abs(sl))),
                    "mean_e":float(np.mean(sl)),"rms_e":float(np.sqrt(np.mean(sl**2))),
                    "half_range_e":float((np.max(sl)-np.min(sl))/2),
                    "alternating_component":float(abs(np.mean(even)-np.mean(odd))/2) if len(even) and len(odd) else None,
                    "theta_start":float(zs[0,1]),"theta_end":float(zs[-1,1]),
                    "theta_range":float(np.ptp(zs[:,1])),"K_min":float(np.min(KK[lo:hi+1])),
                    "K_max":float(np.max(KK[lo:hi+1])),"lag2_max":float(np.max(pv)) if len(pv) else None,
                    "lag2_component_max":np.max(np.abs(z[max(2,lo):hi+1]-z[max(2,lo)-2:hi-1]),axis=0).tolist() if hi>=max(2,lo) else None,
                    "nearest_D1_orbit_max":float(np.max(dv)) if ref is not None else None,
                    "abs_r_minus_K_max":float(np.max(np.abs(r-KK[lo:hi+1]))) if model=="ANF" else None}
        checks=[]
        for cp in cfg["measurements"]["checkpoints"]:
            if cp>last:continue
            source_e=ee[:cp];ip=int(np.argmax(np.abs(source_e)))
            checks.append({"H":cp,"source_peak_excludes_final":float(abs(source_e[ip])),"peak_index":ip,
                           "max_abs_e_including_final":float(np.max(np.abs(ee[:cp+1]))),
                           "early":window(0,199),"middle":window(cp//2,cp//2+199),
                           "tail1000":window(cp-999,cp),"tail200":window(cp-199,cp)})
        perturb=[]
        if ref is not None:
            for k in [0,1,2,4,8,16,32,64,128,256,512]:
                if k<=last:
                    perturb.append({"k":k,"phase_point_error":norm(z[k]-((-1.)**k)*ref),
                                    "nearest_orbit_error":float(dist[k]),"e":float(ee[k]),"theta":float(z[k,1])})
        escape=int(np.flatnonzero(dist>1e-3)[0]) if ref is not None and np.any(dist>1e-3) else None
        # Full arrays are retained, CSV is a fixed-rule plotting subset.
        full[case["id"]+"__state"]=z;full[case["id"]+"__e"]=ee;full[case["id"]+"__K"]=KK
        keep=set(range(min(128,last+1)))|set(range(max(0,last-255),last+1))
        for k in range(0,last+1,200):keep.add(k);keep.add(min(k+1,last))
        for cp in checks:
            for k in range(max(0,cp["H"]-2),min(last,cp["H"]+2)+1):keep.add(k)
            for k in range(max(0,cp["peak_index"]-3),min(last,cp["peak_index"]+3)+1):keep.add(k)
            for name in ("early","middle","tail1000","tail200"):
                w=cp[name]
                if w.get("available"):
                    lo,hi=w["start"],w["end"]
                    for ix in [lo+int(np.argmax(ee[lo:hi+1])),lo+int(np.argmin(ee[lo:hi+1]))]:
                        keep.update(range(max(0,ix-3),min(last,ix+3)+1))
        for k in sorted(keep):
            csv_rows.append([case["id"],k,*z[k].tolist(),ee[k],KK[k],dist[k]])
        summaries.append({"case":case,"initial_state":initial.tolist(),"completed_updates":last,
                          "failure":error,"checkpoints":checks,"final_state":z[-1].tolist(),
                          "final_e":float(ee[-1]),"final_K":float(KK[-1]),
                          "final_abs_r_minus_K":float(abs(r-KK[-1])) if model=="ANF" else None,
                          "reference_D1_state":ref.tolist() if ref is not None else None,
                          "perturbation_diagnostics":perturb,"first_nearest_D1_distance_gt_1e_3":escape,
                          "last_antiphase_residual":float(anti[-1]) if len(anti) else None,
                          "csv_rows":len(keep),"units":"dimensionless selected numerical coordinates",
                          "period2_warning":"lag2 residual small also at a fixed point; inspect nonzero tail amplitude/phase distance."})
    if total_updates>cfg["budget"]["total_update_ceiling"]:raise RuntimeError("Budget exceeded")
    rp=Path(result_path);npz=rp.with_name(rp.stem+".full-traces.npz");cs=rp.with_name(rp.stem+".plot-samples.csv")
    np.savez_compressed(npz,**full)
    with cs.open("w",newline="",encoding="ascii") as fcsv:
        w=csv.writer(fcsv);w.writerow(["case_id","k","state0_m_or_x","theta","e","K_local","nearest_D1_orbit_distance"])
        for row in csv_rows:w.writerow(row)
    files=[{"path":"research_runs/"+p.name,"scope":"manuscript","bytes":p.stat().st_size,"sha256":sha(p),"role":role}
           for p,role in [(npz,"Full undecimated float64 state/e/K arrays"),(cs,"Fixed-rule adjacent-pair CSV samples and extrema")]]
    out={"schema":"anf.D2-finite-results/1","work_id":cfg["work_id"],"protocol_sha256":PIN,
         "runtime":{"python":sys.version,"numpy":np.__version__},"D1_reuse":cfg["D1_reuse"],
         "seed_eigenvectors_from_stored_D1_J":vectors,"cases":summaries,
         "case_count":len(summaries),"successful_update_count":total_updates,
         "failure_count":sum(s["failure"] is not None for s in summaries),
         "protocol_completed":all(s["completed_updates"]==s["case"]["horizon"] and s["failure"] is None for s in summaries),
         "data_files":files,"plot_sample_rows":len(csv_rows),
         "scientific_status":"AUTHOR_FINITE_TRAJECTORIES_AND_LOCAL_PROOF_PENDING_INDEPENDENT_SCIENCE",
         "limitations":["No convergence/global self-quenching oracle or open-ended search.",
         "Rounded D1 saddle/linear stable-direction seeds are not exact nonlinear invariant-manifold initialisations.",
         "D1 orbit/root/Jacobian checks reused, not rerun. D2 eigenvector calculation only selects perturbation seeds.",
         "Full binary arrays retained; CSV decimation must not be mistaken for every step.",
         "Exact erf/sinh and erf proxies, not finite-agent/physical-block validation or interval-certified numerics."]}
    rp.write_text(json.dumps(clean(out),indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({k:out[k] for k in ("case_count","successful_update_count","failure_count","protocol_completed","plot_sample_rows")}))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--mode",required=True,choices=["smoke"]);p.add_argument("--args-json",required=True);p.add_argument("--result",required=True)
    a=p.parse_args()
    if json.loads(a.args_json)!={}:raise ValueError("No undeclared args")
    run(a.result)
