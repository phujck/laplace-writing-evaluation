"""Finite D4b actuation checks. No original scripts imported or overwritten.
Chronological controls, exact Fraction references and direct numeric simulation.
"""
import argparse,csv,hashlib,json,math,sys
from fractions import Fraction as Q
from pathlib import Path
import numpy as np
PIN="94030e92d93dd8b52c9c9599673eabb5d540ed4dfca5d1f4efec5c85cd582eb6"
def qi(x):return Q(str(x))
def fl(v):
    if isinstance(v,list):return [fl(x) for x in v]
    return float(v)
def zs(m,n):return [[Q(0) for j in range(n)] for i in range(m)]
def rank(rows,n):
    a=[row[:] for row in rows];k=0
    for j in range(n):
        p=next((i for i in range(k,len(a)) if a[i][j]),None)
        if p is None:continue
        a[k],a[p]=a[p],a[k];d=a[k][j];a[k]=[v/d for v in a[k]]
        for i in range(len(a)):
            if i!=k and a[i][j]:
                d=a[i][j];a[i]=[x-d*y for x,y in zip(a[i],a[k])]
        k+=1
        if k==len(a):break
    return k
def solve(a,b):
    n=len(b);m=[a[i][:]+[b[i]] for i in range(n)]
    for j in range(n):
        p=next(i for i in range(j,n) if m[i][j])
        m[j],m[p]=m[p],m[j];d=m[j][j];m[j]=[v/d for v in m[j]]
        for i in range(n):
            if i!=j:
                d=m[i][j];m[i]=[x-d*y for x,y in zip(m[i],m[j])]
    return [r[-1] for r in m]
def exact_opt(M,b,weights,H):
    rk=rank(M,H)
    reachable=rank([row+[x] for row,x in zip(M,b)],H+1)==rk
    if not reachable:return {"rank":rk,"reachable":False,"u":None,"effort":None}
    basis=[];idx=[]
    for i,row in enumerate(M):
        if rank(basis+[row],H)>len(basis):basis.append(row);idx.append(i)
    if not basis:u=[Q(0)]*H
    else:
        W=[[sum((x*y/w for x,y,w in zip(r,s,weights)),Q(0)) for s in basis] for r in basis]
        lam=solve(W,[b[i] for i in idx])
        u=[sum((basis[i][t]*lam[i] for i in range(len(basis))),Q(0))/weights[t] for t in range(H)]
    residual=[sum((x*y for x,y in zip(row,u)),Q(0))-x for row,x in zip(M,b)]
    assert not any(residual)
    return {"rank":rk,"reachable":True,"u":u,"effort":sum((w*x*x for w,x in zip(weights,u)),Q(0))}
def norm(x):
    a=np.asarray(x);return float(np.max(np.abs(a))) if a.size else 0.
def clean(x):
    if isinstance(x,Q):return str(x)
    if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,np.ndarray):return clean(x.tolist())
    if isinstance(x,(np.integer,np.floating)):return x.item()
    return x
def run(path):
    raw=Path("D4b/v1/protocol-source-inputs.json").read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PIN:raise ValueError("protocol changed")
    cfg=json.loads(raw)
    proof=Path("D4b/v1/actuation-proof.md").read_bytes()
    if hashlib.sha256(proof).hexdigest()!=cfg["derivation_before_checks"]["sha256"]:raise ValueError("proof changed")
    checks=[];cases=[];rows=[];exceptions=[]
    def check(name,err,tol=1e-9):
        checks.append({"id":name,"error":float(err),"tolerance":tol,"passed":bool(math.isfinite(err) and err<=tol)})
    for p in cfg["cases"]:
      try:
        L,H=p["L"],p["H"];a,c,g=map(qi,(p["a"],p["c"],p["g"]))
        T=list(map(qi,p.get("state_scale",["1"]*L)))
        weights=list(map(qi,p.get("weights",[p["w"]]*H)))
        assert len(weights)==H and all(w>0 for w in weights)
        A=zs(L,L)
        for i in range(L):
            A[i][i]=a
            if i:A[i][i-1]=c*T[i]/T[i-1]
        B=[g*T[0]]+[Q(0)]*(L-1)
        ell=[Q(0)]*(L-1)+[1/T[-1]]
        x0=[qi(x)*s for x,s in zip(p["x0"],T)]
        autonomous=x0[:]
        for t in range(H):autonomous=[sum((v*x for v,x in zip(row,autonomous)),Q(0)) for row in A]
        # Independent exact binomial impulse columns, converted to chronology.
        powers=[]
        for j in range(H):
            powers.append([g*T[i]*math.comb(j,i)*a**(j-i)*c**i if i<=j else Q(0) for i in range(L)])
        Cq=[[powers[H-1-t][i] for t in range(H)] for i in range(L)]
        An,Bn,elln,xn=map(lambda x:np.array(fl(x),float),(A,B,ell,x0))
        P=np.eye(L);ascending=[]
        for j in range(H):ascending.append(P@Bn);P=An@P
        C=np.column_stack(ascending[::-1]) if H else np.zeros((L,0))
        check(p["id"]+":impulse",norm(C-np.array(fl(Cq),float).reshape(L,H)),1e-12)
        exact_rank=rank(Cq,H)
        if g and c:expected_rank=min(H,L)
        elif g and H:expected_rank=1
        else:expected_rank=0
        check(p["id"]+":rank_reference",abs(exact_rank-expected_rank),0)
        W=C@C.T
        Wsum=sum((np.outer(v,v) for v in ascending),np.zeros((L,L)))
        check(p["id"]+":Gramian",norm(W-Wsum),1e-12)
        rec={"case":p,"A":An,"B":Bn,"ell":elln,"C_chronological":C,"W_unweighted":W,"rank_exact":exact_rank,"autonomous_terminal":fl(autonomous),"tasks":[]}
        for task in p["tasks"]:
            full=task["kind"]=="full"
            target=[qi(x)*s for x,s in zip(task["target"],T)] if full else [qi(task["delta"])]
            Mq=Cq if full else [[sum((ell[i]*Cq[i][t] for i in range(L)),Q(0)) for t in range(H)]]
            b=[x-y for x,y in zip(target,autonomous)] if full else [target[0]-sum((x*y for x,y in zip(ell,autonomous)),Q(0))]
            ex=exact_opt(Mq,b,weights,H)
            M=np.array(fl(Mq),float).reshape(len(b),H);bn=np.array(fl(b));wn=np.array(fl(weights))
            F=M/np.sqrt(wn)[None,:] if H else M.copy()
            U,s,Vh=np.linalg.svd(F,full_matrices=True)
            tol=(float(s[0])*1e-12) if len(s) else 0.
            rn=int(np.sum(s>tol))
            check(p["id"]+":"+task["id"]+":rank_svd",abs(rn-ex["rank"]),0)
            v=Vh[:rn].T@((U[:,:rn].T@bn)/s[:rn]) if rn else np.zeros(H)
            u=v/np.sqrt(wn) if H else v
            residual=norm(M@u-bn)
            WG=(M/wn[None,:])@M.T if H else np.zeros((len(b),len(b)))
            pinv=np.linalg.pinv(WG,rcond=1e-12,hermitian=True)
            unchecked=float(bn@pinv@bn)
            tr={"task":task,"terminal_target_in_coordinates":fl(target),"required_defect":fl(b),"reachable":ex["reachable"],"exact_rank":ex["rank"],"weighted_singular_values":s,"weighted_output_Gramian":WG,"unchecked_pseudoinverse_quadratic":unchecked,"least_squares_residual":residual,"status":"REACHABLE" if ex["reachable"] else "UNREACHABLE","minimum_effort":None,"extended_minimum":"+infinity" if not ex["reachable"] else None,"least_squares_control":u,"exact_reference":{"rank":ex["rank"],"reachable":ex["reachable"],"u":None if ex["u"] is None else [str(z) for z in ex["u"]],"effort":None if ex["effort"] is None else str(ex["effort"])}}
            state=xn.copy();trace=[state.copy()]
            for ut in u:state=An@state+Bn*ut;trace.append(state.copy())
            tr["forward_states_for_displayed_control"]=trace
            directed=state if full else np.array([elln@state])
            tr["terminal_residual"]=norm(directed-np.array(fl(target)))
            if ex["reachable"]:
                cost=float(np.dot(wn*u,u));ug=(M.T@pinv@bn)/wn if H else np.zeros(0)
                ex_cost=float(ex["effort"])
                check(p["id"]+":"+task["id"]+":control_reference",norm(u-np.array(fl(ex["u"]))),1e-9)
                check(p["id"]+":"+task["id"]+":effort_reference",abs(cost-ex_cost)/max(1.,abs(ex_cost)),1e-9)
                check(p["id"]+":"+task["id"]+":terminal",tr["terminal_residual"],1e-9)
                check(p["id"]+":"+task["id"]+":Gramian_control",norm(u-ug),1e-9)
                stationarity=norm(Vh[rn:]@(np.sqrt(wn)*u)) if H else 0.
                check(p["id"]+":"+task["id"]+":stationarity",stationarity,1e-9)
                tr.update(minimum_effort=cost,extended_minimum=str(ex["effort"]),optimal_control=u,stationarity_residual=stationarity,Gramian_control=ug,effort_from_Gramian=unchecked)
            else:
                tr["warning"]="Least-squares displayed control and unchecked pinv number are NOT feasible/optimum controls or constrained cost."
            rec["tasks"].append(tr)
            rows.append({"case":p["id"],"L":L,"H":H,"a":p["a"],"c":p["c"],"g":p["g"],"task":task["id"],"reachable":ex["reachable"],"rank":ex["rank"],"effort":tr["minimum_effort"],"exact_effort":tr["exact_reference"]["effort"],"residual":tr["terminal_residual"],"unchecked_pinv":unchecked})
        cases.append(rec)
      except Exception as exc:
        exceptions.append({"case":p["id"],"type":type(exc).__name__,"message":str(exc)})
    index={r["case"]["id"]:{t["task"]["id"]:t for t in r["tasks"]} for r in cases}
    def E(case,task):return index[case][task]["minimum_effort"]
    # Explicit analytic predictions, tested against computed quantities, never assigned.
    for H,eo,ef in [(2,Q(4),Q(8)),(3,Q(4,5),Q(2)),(4,Q(2,7),Q(4,5))]:
        for task,expect in [("top",eo),("apex",ef)]:check("rational_L2_H"+str(H)+":"+task,abs(E("L2_a1_H"+str(H),task)-float(expect)))
    for H in [2,3]:check("nonstrict_H"+str(H),abs(E("L2_a1_H"+str(H),"nonstrict_target")-20))
    for task in ["top","apex","ones"]:
        base=E("L2_a1_H3",task)
        for cid,mult in [("target_times2",4),("gain_times2",.25),("weight_times3",3),("state_units_T23",1),("input_units_kappa2",1)]:
            check("scaling:"+cid+":"+task,abs(E(cid,task)-mult*base))
    for L in [2,3]:
        for a in ["0","1p2","1"]:
            at=E("L"+str(L)+"_a"+a+"_H"+str(L),"top")
            late=E("L"+str(L)+"_a"+a+"_H"+str(2*L),"top")
            if a=="0":check("shift_horizon_top_L"+str(L),abs(at-late))
            else:check("persistent_strict_top_L"+str(L)+"a"+a,0. if late<at else 1.,0.)
            for H in [L,2*L]:
                cid="L"+str(L)+"_a"+a+"_H"+str(H)
                check("relaxation:"+cid,max(0.,E(cid,"top")-E(cid,"apex")))
                if a=="0":check("shift_coincidence:"+cid,abs(E(cid,"top")-E(cid,"apex")))
    outpath=Path(path)
    csvpath=outpath.with_suffix(".tasks.csv")
    with csvpath.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    data={"path":str(csvpath.name),"scope":"manuscript","bytes":csvpath.stat().st_size,"sha256":hashlib.sha256(csvpath.read_bytes()).hexdigest(),"role":"Complete task summary CSV, no sampling/decimation"}
    out={"schema":"anf.D4b-finite-results/1","work":cfg["work"],"protocol_sha256":PIN,"proof_sha256":cfg["derivation_before_checks"]["sha256"],"runtime":{"python":sys.version,"numpy":np.__version__},"case_count":len(cases),"task_count":len(rows),"reachable_count":sum(r["reachable"] for r in rows),"unreachable_count":sum(not r["reachable"] for r in rows),"check_count":len(checks),"failed_check_count":sum(not x["passed"] for x in checks),"exception_count":len(exceptions),"exceptions":exceptions,"checks":checks,"cases":cases,"data_files":[data],"scientific_status":"AUTHOR_FINITE_CONSISTENCY_NOT_INDEPENDENT_SCIENCE_OR_FORMAL_VERIFICATION","limitations":["Exact Fraction reference is independent author arithmetic, not a proof-assistant certificate.","Unreachable targets are retained with null cost/+infinity and explicitly unconstrained least-squares diagnostics.","No original R5 module/sweep/plot rerun, population simulation, maintenance, physical-energy calibration or static-actuator coupling validation.","No figure/media generated, all controls/forward states and task values retained without decimation."]}
    outpath.write_text(json.dumps(clean(out),indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:out[k] for k in ["case_count","task_count","reachable_count","unreachable_count","check_count","failed_check_count","exception_count"]}))
    return not exceptions and all(c["passed"] for c in checks)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--mode",choices=["smoke"],required=True);p.add_argument("--args-json",required=True);p.add_argument("--result",required=True);a=p.parse_args()
    if json.loads(a.args_json)!={}:raise ValueError("No arguments declared")
    sys.exit(0 if run(a.result) else 1)
