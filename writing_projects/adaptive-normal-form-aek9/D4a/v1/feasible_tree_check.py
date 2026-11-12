"""D4a finite exact-tree and algebra checks. New author-run evidence, not independent science.
No original script execution, dynamics, populations, matrix/actuator sweep or network.
"""
import argparse, hashlib, json, math, sys
from fractions import Fraction as F
from functools import lru_cache
from pathlib import Path
SNAPSHOT_SHA="78e1f518d28d229e842a8352110d249df62ec0fd7307922695ce3be017b036cc"
def frac(v): return F(str(v))
def exact_power(x,p):
    if p.denominator==1:return x**p.numerator
    if p.denominator==2:
        a,b=math.isqrt(x.numerator),math.isqrt(x.denominator)
        if a*a!=x.numerator or b*b!=x.denominator:raise ValueError("Not an exact square")
        return F(a,b)**p.numerator
    raise ValueError("Unsupported finite control power")
def enc(x): return {"numerator":str(x.numerator),"denominator":str(x.denominator),"float":float(x)}
@lru_cache(None)
def block_slope(n):
    if n<1:raise ValueError("Invalid span")
    return F(n*math.comb(n-1,(n-1)//2),2**(n-1))
def compositions(k):
    if k==0:
        yield ()
    else:
        for a in range(1,k+1):
            for tail in compositions(k-a):
                yield (a,)+tail
def classify(q): return "stable" if q<1 else ("boundary" if q==1 else "outside_strict")
def main(result):
    raw=Path("D4a/v1/source-inputs.json").read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SNAPSHOT_SHA:raise ValueError("Input pin mismatch")
    cfg=json.loads(raw); ctrls=cfg["controls"]
    H=cfg["resource_example"]["H"]
    B=frac(cfg["resource_example"]["Emax_over_E0"])
    csq=frac(cfg["resource_example"]["c_squared"])
    budget_depths=[L for L in range(1,H+1) if csq**(-(L-1))<=B]
    rows=[];sizes=[];tests=[];mismatches=[];ambiguities=[]
    for k in range(cfg["architecture"]["k_min"],cfg["architecture"]["k_max"]+1):
        N=3**k; partrows=[]
        for exps in compositions(k):
            spans=[3**a for a in exps];L=len(exps)
            g=math.prod([block_slope(n) for n in spans])
            ratios={c["id"]:frac(c["eta"])*g**c["nu"] for c in ctrls}
            states={key:classify(q) for key,q in ratios.items()}
            row={"k":k,"N":N,"exponents":list(exps),"spans":spans,"L":L,
                 "slope_over_beta":enc(g),
                 "normalised_gain_float":{key:float(q) for key,q in ratios.items()},
                 "exact_gain_states":states,
                 "resource_cost_over_E0":enc(csq**(-(L-1))),
                 "conditional_resource_admissible":L<=H and csq**(-(L-1))<=B}
            rows.append(row);partrows.append((g,row))
        tests.append({"name":f"k{k}_composition_count","pass":len(partrows)==2**(k-1)})
        tests.append({"name":f"k{k}_product_and_depth","pass":all(math.prod(r["spans"])==N and 1<=r["L"]<=k and min(r["spans"])>=3 for _,r in partrows)})
        flat=next(g for g,r in partrows if r["L"]==1)
        tri=next(g for g,r in partrows if r["L"]==k)
        tests.append({"name":f"k{k}_flat_identity","pass":flat==block_slope(N)})
        tests.append({"name":f"k{k}_ternary_chain_identity","pass":tri==F(3,2)**k})
        depths=[]
        for L in range(1,k+1):
            group=[(g,r) for g,r in partrows if r["L"]==L]
            mn=min(g for g,_ in group);mx=max(g for g,_ in group)
            depths.append({"L":L,"architecture_count":len(group),"min_slope_over_beta":enc(mn),
                           "max_slope_over_beta":enc(mx),
                           "minimiser_exponents":[r["exponents"] for g,r in group if g==mn]})
        exact={}
        gauss={}
        for c in ctrls:
            cid=c["id"]
            sr=[r for g,r in partrows if r["exact_gain_states"][cid]=="stable"]
            vr=[r for r in sr if r["conditional_resource_admissible"]]
            exact[cid]={"stable_architecture_count":len(sr),
                        "stable_depths":sorted({r["L"] for r in sr}),
                        "conditionally_viable_depths":sorted({r["L"] for r in vr}),
                        "conditionally_viable_architecture_count":len(vr)}
            gs=[]
            for L in range(1,H+1):
                proxy_slope=math.sqrt(N)*(2/math.pi)**(L/2)
                ratio=float(frac(c["eta"]))*proxy_slope**c["nu"]
                ambiguous=abs(ratio-1)<=cfg["oracles"]["floating_proxy_boundary_tolerance"]
                state="undetermined_float_boundary" if ambiguous else ("stable" if ratio<1 else "outside_strict")
                if ambiguous:ambiguities.append({"k":k,"control":cid,"L":L,"ratio":ratio})
                gs.append({"L":L,"slope":proxy_slope,"normalised_gain":ratio,"state":state,
                           "resource_admissible":L in budget_depths,"factor_depth_cap_admissible":L<=k})
            aw=[v["L"] for v in gs if v["state"]=="stable" and v["resource_admissible"]]
            capped=[L for L in aw if L<=k]
            gauss[cid]={"depth_checks":gs,"abstract_budget_window":aw,
                        "window_after_product_depth_cap":capped}
            if aw and not vr:
                mismatches.append({"k":k,"N":N,"control":cid,
                                   "gaussian_abstract_budget_window":aw,
                                   "gaussian_window_after_depth_cap":capped,
                                   "exact_feasible_set_empty":True,
                                   "exact_minimum_slope":enc(min(g for g,r in partrows)),
                                   "min_exact_gain_ratio":float(frac(c["eta"])*min(g for g,r in partrows)**c["nu"])})
        sizes.append({"k":k,"N":N,"architectures":len(partrows),"depth_cap":k,
                      "flat_slope_over_beta":enc(flat),"ternary_chain_slope_over_beta":enc(tri),
                      "min_slope_over_beta":enc(min(g for g,r in partrows)),
                      "max_slope_over_beta":enc(max(g for g,r in partrows)),
                      "by_depth":depths,"exact_controls":exact,"gaussian_controls":gauss})
    reciprocal=[]
    for c in cfg["reciprocal_controls"]:
        p=frac(c["p"]);d=frac(c["d"]); kr,kc,nref=map(frac,[c["Kref"],c["Kc"],c["Nref"]]);L=c["L"]
        flat=nref*exact_power(kc/kr,1/p)
        critical=nref*exact_power(kc/(kr*d**(L-1)),1/p)
        predicted=exact_power(d,-F(L-1)/p)
        reciprocal.append({**c,"Nc_flat":enc(flat),"Nc_depth":enc(critical),
                           "size_multiplier":enc(critical/flat),"derived_multiplier":enc(predicted),
                           "gain_at_critical":enc(kr*exact_power(critical/nref,p)*d**(L-1)),
                           "incorrect_no_reciprocal_multiplier":enc(d**(-(L-1)))})
    tests.append({"name":"reciprocal_exact_ratios","pass":[r["size_multiplier"]["float"] for r in reciprocal]==[16.,4.,2.]})
    boundary=[]
    for v in cfg["boundary_controls"]["flat_gain_ratios"]:
        ratio=frac(v);q=ratio.numerator.bit_length()-ratio.denominator.bit_length()
        if ratio!=F(2)**q:raise ValueError("Boundary controls must be dyadic")
        strict_formula=max(1,q+2);weak_formula=max(1,q+1)
        strict=[L for L in range(1,17) if ratio*F(1,2)**(L-1)<1]
        weak=[L for L in range(1,17) if ratio*F(1,2)**(L-1)<=1]
        boundary.append({"flat_gain_ratio":v,"x_exact":q,"strict_formula_Lmin":strict_formula,
                         "weak_formula_Lmin":weak_formula,"strict_enumerated_Lmin":min(strict),
                         "weak_enumerated_Lmin":min(weak),
                         "gain_ratio_at_strict_Lmin":enc(ratio*F(1,2)**(strict_formula-1))})
        tests.append({"name":"strict_weak_boundary_"+v,"pass":min(strict)==strict_formula and min(weak)==weak_formula})
    starting=[]
    for c in cfg["starting_scale_controls"]:
        p=frac(c["p"]); kr=frac(c["Kref"]);nr=frac(c["Nref"])
        vals=[{"N":v,"gain_ratio":enc(kr*exact_power(frac(v)/nr,p)),
               "state":classify(kr*exact_power(frac(v)/nr,p))} for v in c["N_values"]]
        starting.append({**c,"N_start_gain_ratio":enc(kr*exact_power(frac(c["N_start"])/nr,p)),"values":vals})
    tests.append({"name":"negative_p_start_not_all_stable","pass":[v["state"] for v in starting[0]["values"]]==["outside_strict","boundary","stable"]})
    tests.append({"name":"no_unary_or_binary_attenuation_exact","pass":block_slope(1)==1 and block_slope(2)==1})
    tests.append({"name":"total_compositions","pass":len(rows)==255})
    # Symbolic odd-block lower bound checked exactly for every used span:
    used=[3**a for a in range(1,9)]
    tests.append({"name":"odd_span_slope_lower_bound_finite","pass":all(block_slope(n)**2>=F(n+1,2) for n in used)})
    resource_controls=[]
    for HH,BB in [(0,F(128)),(8,F(1,2)),(8,F(1)),(8,F(2)),(8,F(4)),(8,F(128))]:
        feasible=[L for L in range(1,HH+1) if F(2)**(L-1)<=BB]
        resource_controls.append({"H":HH,"budget_ratio":str(BB),"depths":feasible,
                                  "interpretation":"terminal shift cost inequality only, no actuator variant simulation"})
    out={"schema":"anf.D4a-results/1","work_id":cfg["work_id"],
         "source_input_sha256":SNAPSHOT_SHA,"runtime":{"python":sys.version,"arithmetic":"math.comb plus fractions.Fraction, standard library only"},
         "architecture_assumptions":cfg["architecture"],"controls":ctrls,
         "resource_definition_only":cfg["resource_example"],
         "block_slopes":[{"span":n,"exact_slope":enc(block_slope(n))} for n in [1,2]+used],
         "by_size":sizes,"architectures":rows,"mismatches":mismatches,
         "reciprocal_controls":reciprocal,"boundary_controls":boundary,
         "starting_scale_controls":starting,"resource_inequality_controls":resource_controls,
         "floating_proxy_boundary_ambiguities":ambiguities,"oracle_tests":tests,
         "all_structural_algebra_oracles_pass":all(t["pass"] for t in tests),
         "architecture_count":len(rows),"mismatch_count":len(mismatches),
         "mismatch_count_after_depth_cap":sum(bool(v["gaussian_window_after_depth_cap"]) for v in mismatches),
         "scientific_status":"AUTHOR_COMPUTED_FINITE_EXACT_SLOPES_INDEPENDENT_REVIEW_PENDING",
         "limitations":["Exact rational gain comparisons within declared homogeneous iid odd-majority product trees only.",
         "Gaussian proxy comparisons are floating and not exact block maps or interval certificates.",
         "Illustrative dimensionless eta and nu controls are not empirical controller estimates.",
         "No trajectories, stochastic/local-attractor inference, actuaror-variant or persistent steering validation.",
         "D2 and D4b are explicitly queued, not executed."]}
    Path(result).write_text(json.dumps(out,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"architecture_count":len(rows),"all_structural_algebra_oracles_pass":out["all_structural_algebra_oracles_pass"],
                      "mismatch_count":len(mismatches),"mismatch_count_after_depth_cap":out["mismatch_count_after_depth_cap"],
                      "floating_ambiguities":len(ambiguities)}))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--mode",required=True,choices=["smoke"])
    p.add_argument("--args-json",required=True);p.add_argument("--result",required=True);a=p.parse_args()
    if json.loads(a.args_json)!={}:raise ValueError("No undeclared args")
    main(a.result)
