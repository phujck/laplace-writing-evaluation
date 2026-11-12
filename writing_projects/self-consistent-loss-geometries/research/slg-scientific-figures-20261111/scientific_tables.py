"""Finite scientific figure tables. No original outputs or manuscript source overwritten."""
from __future__ import annotations
import argparse, ast, csv, hashlib, json, math, platform, sys
from pathlib import Path
import numpy as np

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def mse(x,y,z): return float(np.mean((y-z*x)**2))
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--mode",required=True)
    ap.add_argument("--args-json",required=True); ap.add_argument("--result",required=True)
    args=ap.parse_args(); assert args.mode=="full" and json.loads(args.args_json)=={}
    here=Path(__file__).resolve().parent; project=here.parents[1]
    protocol_path=project/"evidence/SLG_VISUAL_PRODUCTION_2026-11-11/finite-figure-protocol.json"
    cfg=json.loads(protocol_path.read_text())
    original=here/"original_numerical_demonstrations.py"
    accepted=project/"research/slg-analytic-20261111-v2/finite_checks.py"
    assert digest(original)=="ebe2e17c4803b312197fd5ce415cae59c29ecd7ba62256cf7f2cf7aa86c5b6d7"
    assert digest(accepted)=="8f39b070b310baaaa58e6b3824ab7a59c0c86a9c8f5d1f3271e00b4a690a6ce7"
    result=Path(args.result); assert result.is_absolute()
    outdir=here/"outputs"/result.stem
    outdir.mkdir(parents=True,exist_ok=False)
    files=[]
    def save(name,rows):
        path=outdir/name
        assert rows
        with path.open("w",newline="",encoding="utf-8") as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        desc=dict(id=name.removesuffix(".csv"),path=str(path.relative_to(project)),scope="project",
                  sha256=digest(path),bytes=path.stat().st_size,rows=len(rows),columns=list(rows[0]))
        files.append(desc); return desc
    tree=ast.parse(original.read_text())
    nodes=[n for n in tree.body if (isinstance(n,ast.FunctionDef) and n.name in ["generate_regime_data","run_two_scale_agent"])
           or (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="SHIFT_SCHEDULE" for t in n.targets))]
    ns={"np":np}; exec(compile(ast.Module(body=nodes,type_ignores=[]),"<pinned-original-numerical-functions>","exec"),ns)
    old=ast.parse(accepted.read_text()); mainnode=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=="main")
    oldloop=next(n for n in mainnode.body if isinstance(n,ast.For) and isinstance(n.iter,ast.Call)
        and isinstance(n.iter.func,ast.Name) and n.iter.func.id=="range" and len(n.iter.args)==2
        and isinstance(n.iter.args[1],ast.Name) and n.iter.args[1].id=="n")
    start=next(i for i,n in enumerate(oldloop.body) if isinstance(n,ast.Assign) and isinstance(n.value,ast.Name) and n.value.id=="state1")
    refcode=compile(ast.Module(body=oldloop.body[start:],type_ignores=[]),"<accepted-v1-selection-application>","exec")
    p=cfg["accounting"]; beta=p["beta"]; alpha=p["partial_step"]; ridge=p["ridge"]
    window=p["window"]; minfit=p["minimum_fit_points"]; sigma=cfg["data"]["noise_sigma"]
    evalstart=cfg["data"]["evaluation_start"]; n=cfg["finite_budget"]["steps"]
    prices=cfg["finite_budget"]["prices"]; seeds=cfg["finite_budget"]["seeds"]
    names=["Legacy v0","Rolling control","Priced v1"]
    shift_times=[s[0] for s in cfg["data"]["shifts"]]
    records=[]; ledgers=[]; track_paths={}; reference=[]; max_v1_gain_error=0.; promoted_counts={name:0 for name in names}
    def manual(x,y,c,name):
        prior=np.ones(n); post=np.ones(n); promote=np.zeros(n,dtype=bool); errors=np.zeros(n)
        gains=[]; score_gaps=[]; realised=[]; rows=[]; candidate_error=0.; theta=1.
        for t in range(1,n):
            prior[t]=theta; errors[t]=y[t]-theta*x[t]
            begin=max(0,t-window+1); xw=x[begin:t+1]; yw=y[begin:t+1]
            fit=float(np.sum(xw*yw)/(np.sum(xw*xw)+ridge)) if len(xw)>=minfit else theta
            before_loss=mse(xw,yw,theta)
            full_gain=max(0.,before_loss-mse(xw,yw,fit)) if len(xw)>=minfit else 0.
            proxy=.1*min(errors[t]**2,sigma**2)
            if name=="Legacy v0":
                target=float(np.clip(y[t]/x[t],-1.5,3.5)) if abs(x[t])>.15 else fit
                candidate=theta+alpha*(target-theta)
                g0,g1=proxy,full_gain
            elif name=="Rolling control":
                candidate=theta+alpha*(fit-theta); g0,g1=proxy,full_gain
            else:
                candidate=theta+alpha*(fit-theta); g0=0.; g1=before_loss-mse(xw,yw,candidate)
            actual_candidate_gain=before_loss-mse(xw,yw,candidate)
            gap=beta*(g1-g0)-c; choice=gap>0
            newtheta=candidate if choice else theta
            gain=before_loss-mse(xw,yw,newtheta)
            if name=="Priced v1":
                candidate_error=max(candidate_error,abs(g1-actual_candidate_gain),abs(gain-(g1 if choice else 0.)))
            promote[t]=choice; post[t]=newtheta
            gains.append(g1); score_gaps.append(gap); realised.append(gain)
            rows.append(dict(t=t,theta_before=float(theta),theta0=float(theta),theta1=float(candidate),
                gain0=float(g0),gain1=float(g1),actual_candidate1_gain=float(actual_candidate_gain),
                cost0=0.,cost1=c,score_gap=float(gap),chosen=int(choice),theta_after=float(newtheta),
                realised_window_gain=float(gain),pre_action_error=float(errors[t]),horizon_start=begin,horizon_end=t))
            theta=newtheta
        errors[0]=y[0]-x[0]
        return dict(prior=prior,post=post,promote=promote,errors=errors,rows=rows,ledger_error=candidate_error)
    for seed in seeds:
        x,y,truth=ns["generate_regime_data"](t_steps=n,sigma=sigma,seed=seed)
        evalmask=np.arange(n)>=evalstart
        outside=evalmask.copy()
        for shift in shift_times: outside[shift:shift+65]=False
        for c in prices:
            for name in names:
                path=manual(x,y,c,name); pre=path["prior"]; flags=path["promote"]
                promoted_counts[name]+=int(flags.sum())
                max_v1_gain_error=max(max_v1_gain_error,path["ledger_error"])
                recovery=[]
                for shift in shift_times:
                    threshold=.2*abs(truth[shift]-truth[shift-1]); delay=65
                    for t in range(shift,min(shift+61,n-4)):
                        if np.all(np.abs(pre[t:t+5]-truth[t:t+5])<=threshold):
                            delay=t-shift; break
                    recovery.append(delay)
                rr=path["rows"]; evaluated=rr[evalstart-1:]
                raw_gaps=[abs(r["gain1"]-r["actual_candidate1_gain"]) for r in evaluated]
                record=dict(seed=seed,policy=name,price=c,
                    prequential_mse=float(np.mean(path["errors"][evalmask]**2)),
                    latent_mse=float(np.mean((pre[evalmask]-truth[evalmask])**2)),
                    noise_oracle_mse=float(np.mean((y[evalmask]-truth[evalmask]*x[evalmask])**2)),
                    never_update_mse=float(np.mean((y[evalmask]-x[evalmask])**2)),
                    promotion_count=int(flags[evalmask].sum()),
                    promotion_rate=float(np.mean(flags[evalmask])),
                    promotion_cost_sum=float(c*flags[evalmask].sum()),
                    off_transition_promotion_rate=float(flags[outside].sum()/outside.sum()),
                    recovery_failure_fraction=float(np.mean(np.array(recovery)==65)),
                    recovery_censored_mean=float(np.mean(recovery)),
                    recovery_delays="|".join(map(str,recovery)),
                    realised_window_gain_sum=float(sum(row["realised_window_gain"] for row in evaluated)),
                    mean_abs_candidate_gain_mismatch=float(np.mean(raw_gaps)),
                    max_abs_candidate_gain_mismatch=float(max(raw_gaps)),ledger_error=path["ledger_error"])
                records.append(record)
                if seed==0 and c==.06:
                    ledgers.extend([dict(seed=seed,policy=name,price=c,**row) for row in rr])
                if seed==0 and name=="Priced v1" and c in [.005,.06,.4]:
                    track_paths[c]=(pre.copy(),truth.copy())
                if seed==0 and name=="Legacy v0":
                    rp,_,rf=ns["run_two_scale_agent"](x,y,0.,c,beta=beta,window=window,adapt_rate=alpha,sigma=sigma)
                    error=float(np.max(np.abs(rp-path["post"])))
                    assert error<=1e-12 and np.array_equal(rf,flags)
                    reference.append(dict(policy=name,price=c,max_state_error=error,decisions_equal=True))
                if seed==0 and name=="Priced v1" and c in [.005,.06,.4]:
                    env=dict(np=np,mse=mse,xx=x,yy=y,n=n,state1=1.,alpha=alpha,beta=beta,ridge=ridge,
                             a={"costs":[0.,c]},predicted_applied=[],measured_equal=[],no_update_g=[],v1_rows=[])
                    for t in range(1,n):
                        env["t"]=t; begin=max(0,t-window+1)
                        env["xw"]=x[begin:t+1];env["yw"]=y[begin:t+1];exec(refcode,env)
                    refstates=np.array([1.]+[row["theta_after"] for row in env["v1_rows"]])
                    refchoices=np.array([False]+[bool(row["chosen"]) for row in env["v1_rows"]])
                    error=float(np.max(np.abs(refstates-path["post"])))
                    assert error<=1e-12 and np.array_equal(refchoices,flags)
                    reference.append(dict(policy=name,price=c,max_state_error=error,decisions_equal=True))
    assert max_v1_gain_error<=1e-12
    save("per_stream_metrics.csv",records); save("representative_action_ledgers.csv",ledgers)
    def values(name,c,key): return np.array([r[key] for r in records if r["policy"]==name and r["price"]==c],float)
    risk=[];rate=[];failure=[];paired=[];off=[]
    for c in prices:
        riskrow={"Price":c,"Log10 price":math.log10(c)};raterow=dict(riskrow);failrow=dict(riskrow);offrow=dict(riskrow)
        pair={"Price":c}
        for name in names:
            for target,key in [(riskrow,"prequential_mse"),(raterow,"promotion_rate"),(failrow,"recovery_failure_fraction"),(offrow,"off_transition_promotion_rate")]:
                v=values(name,c,key);target[name]=float(v.mean());target[name+" SE"]=float(v.std(ddof=1)/math.sqrt(len(v)))
            if name!="Legacy v0":
                delta=values(name,c,"prequential_mse")-values("Legacy v0",c,"prequential_mse")
                pair[name+" minus Legacy MSE"]=float(delta.mean())
                pair[name+" paired SE"]=float(delta.std(ddof=1)/math.sqrt(len(delta)))
        riskrow["Noise oracle"]=float(values(names[0],c,"noise_oracle_mse").mean())
        riskrow["Never update"]=float(values(names[0],c,"never_update_mse").mean())
        risk.append(riskrow);rate.append(raterow);failure.append(failrow);paired.append(pair);off.append(offrow)
    save("prediction_risk_curve.csv",risk);save("promotion_rate_curve.csv",rate)
    save("recovery_failure_curve.csv",failure);save("off_transition_curve.csv",off);save("paired_differences.csv",paired)
    tracking=[]
    for t in range(n):
        tracking.append({"Time":t,"True slope":float(track_paths[.06][1][t]),
            "v1 price 0.005":float(track_paths[.005][0][t]),"v1 price 0.06":float(track_paths[.06][0][t]),
            "v1 price 0.4":float(track_paths[.4][0][t])})
    save("priced_policy_tracking.csv",tracking)
    reg=cfg["register"]; register=[]
    for theta in np.linspace(*reg["theta_range"],reg["points"]):
        ds=2*(1-np.cos(theta));A=ds*(.5+reg["gamma"])
        fixed=A/4;arb=min(fixed,reg["eta"]/2);split=min(arb,reg["split_cost"])
        assert split<=arb+1e-14 and arb<=fixed+1e-14
        register.append({"Target separation":float(theta),"Fixed balanced":float(fixed),
                         "Arbitration":float(arb),"Split enabled":float(split),"Split price":reg["split_cost"]})
    save("common_ledger_register.csv",register)
    oc=cfg["or"]; blocks=np.array(oc["external_frozen_blocks"]);sums=blocks.sum(axis=1);orr=[]
    for c in np.linspace(oc["prices_start"],oc["prices_stop"],oc["points"]):
        ps=1/(1+np.exp(-(blocks-c)));haz=np.logaddexp(0.,blocks-c).sum(axis=1)
        q=-np.expm1(-haz); direct=1/(1+np.exp(-(sums-c)))
        exact=1-np.prod(1-ps,axis=1);ce=sums-np.log(np.expm1(haz));avg=ce.mean()
        approx=1/(1+np.exp(-(sums-avg)));mult=ps.sum(axis=1)/q
        assert np.max(abs(q-exact))<1e-12 and np.min(mult)>=1-1e-12 and np.max(mult)<=4+1e-12
        orr.append({"Price":float(c),"Naive mean TV":float(np.mean(abs(q-direct))),
             "Mean intercept TV":float(np.mean(abs(q-approx))),"Max intercept TV":float(np.max(abs(q-approx))),
             "Exact hazard TV":float(np.max(abs(q-exact))),"Mean conditional count":float(mult.mean()),
             "Min conditional count":float(mult.min()),"Max conditional count":float(mult.max()),
             "Single event bound":1.,"Block size bound":4.,"Mean effective intercept":float(avg)})
    save("or_hazard_projection.csv",orr)
    output=dict(schema_version="slg.scientific-figure-result/1",status="COMPLETE",
        scope="Finite predeclared synthetic comparison and analytical figure tables, not independent scientific acceptance.",
        measures=dict(streams=len(seeds),prices=len(prices),policies=len(names),trajectories=len(records),
                      policy_decisions=len(records)*(n-1),max_v1_accounting_error=max_v1_gain_error),
        controls=dict(reference=reference,promoted_counts=promoted_counts,all_reference_tests_passed=True),
        environment=dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),executable=sys.executable),
        source_pins=dict(code=digest(Path(__file__)),protocol=digest(protocol_path),
                         original=digest(original),accepted_v1=digest(accepted)),
        files=files,summary=dict(risk=risk,promotion=rate,recovery_failure=failure,off_transition=off,paired=paired),
        limitations=["Finite twelve streams/six predeclared prices, no optimum selected or large-grid reproduction.",
          "Paired descriptive means and SE across streams, no statistical-significance or generalisation claim.",
          "Observation-window gains are not future viability; prediction is separately measured before update.",
          "Per-promoted-action cost is dimensionless and ignores differential controller computation/maintenance.",
          "Target-change control isolates it from combined action-gain and no-update baseline repricing, not each repair separately.",
          "Recovery uses known synthetic latent slope only for evaluation, not clinical or change-detection validation.",
          "OR schedule is externally frozen and independent, not adaptive path coarse-graining.",
          "Static register optima are nested feasible sets, not unexpected performance superiority."])
    result.write_text(json.dumps(output,indent=2,allow_nan=False)+"\n")
    print(json.dumps(output["measures"]))
if __name__=="__main__": main()
