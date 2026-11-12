"""Bounded algebra checks for reconciliation. Author-origin checks, not independent review.
No imports of original producers, no writes to originals, no benchmarks.
Equations reconstructed from source-pinned assessment, not a rerun of historical scripts.
"""
import argparse, json, math, cmath
def eig2(a,b,c,d):
    tr=a+d
    det=a*d-b*c
    s=cmath.sqrt(tr*tr-4*det)
    return [[z.real,z.imag] for z in ((tr+s)/2,(tr-s)/2)]
p=argparse.ArgumentParser()
p.add_argument("--mode",required=True)
p.add_argument("--args-json",required=True)
p.add_argument("--result",required=True)
args=p.parse_args()
assert args.mode=="smoke" and json.loads(args.args_json)=={}
rows={}
r=.3
rows["constant_gain"]=[{"C":C,"psi":0,"multiplier":r-C,"stable":abs(r-C)<1} for C in (.5,1.3,2.)]
rows["negative_exponent"]=[{"N":N,"K":2/N,"multiplier":r-2/N,"stable":abs(r-2/N)<1} for N in (1,2,10)]
q=math.sqrt(2*.5)
rows["matched_linear"]={"q":q,"alpha":2.,"r":r,"eigenvalues":eig2(r,(1-r)*q,2*q,1-2*q*q),"mismatch_multiplier":r-2*q*q}
# Actual ANF erf/sinh closed-loop symmetric period-two orbit.
N=900; beta=.5; alpha=.01
def f(t): return math.erf(math.sqrt(N/2)*math.sinh(beta*t))
def g(t):
    u=math.sqrt(N/2)*math.sinh(beta*t)
    return 2/math.sqrt(math.pi)*math.exp(-u*u)*math.sqrt(N/2)*beta*math.cosh(beta*t)
def gg(t):
    u=math.sqrt(N/2)*math.sinh(beta*t)
    up=math.sqrt(N/2)*beta*math.cosh(beta*t)
    upp=math.sqrt(N/2)*beta*beta*math.sinh(beta*t)
    return 2/math.sqrt(math.pi)*math.exp(-u*u)*(upp-2*u*up*up)
lo=1e-9; hi=.2
for _ in range(100):
    mid=(lo+hi)/2
    if alpha*g(mid)*f(mid)-(1+r)*mid>0: lo=mid
    else: hi=mid
t=(lo+hi)/2; m=-(1-r)/(1+r)*f(t); e=m-f(t)
m1=r*m+(1-r)*f(t); t1=t+alpha*g(t)*e
a=r; b=(1-r)*g(t); c=alpha*g(t); d=1+alpha*(gg(t)*e-g(t)**2)
ev=eig2(a,b,c,d)
rows["anf_symmetric_cycle"]={"N":N,"theta":t,"m":m,"one_step_to_negative_residual":max(abs(t1+t),abs(m1+m)),"one_step_eigenvalues":ev,"two_step_multipliers":[[complex(*z).real**2-complex(*z).imag**2,2*complex(*z).real*complex(*z).imag] for z in ev],"interpretation":"Existence of a full-loop period-two orbit, not a stable attractor claim."}
lam=math.sqrt(2); psi=.5
rows["depth_exponent"]={"C":.1,"Kc":1.3,"psi":psi,"lambda":lam,"L":3,"Nc_flat":(1.3/.1)**(1/psi),"Nc_correct":(1.3*lam**2/.1)**(1/psi),"Nc_incorrect":(1.3/.1)**(1/psi)*lam**2}
rows["parity"]=[{"N":N,"exact_derivative_beta1":N*math.comb(N-1,(N-1)//2)/2**(N-1),"N_times_relative_correction":N*((N*math.comb(N-1,(N-1)//2)/2**(N-1))/math.sqrt(2*N/math.pi)-1)} for N in (2,3,100,101,500,501)]
# Conditional output-control formula. Two different chains with L=2.
c=.5
rows["control"]={"nilpotent_L2_H2_Wtop":c*c,"nilpotent_L2_H3_Wtop":c*c,"nilpotent_Eunit":1/(c*c),"persistent_A_I_plus_cS_L2_H3_Wtop":5*c*c,"persistent_Eunit_H3":1/(5*c*c)}
# Post-update Phases plant, not ANF matched lagged plant.
b=1.2; s=.4; r=math.exp(-1)
kc=2*(1+r)/((1+r)*b-(1-r)*s)
rows["phases_jury"]={"r":r,"b":b,"s":s,"Kc":kc,"at_boundary_eigenvalues":eig2(r,(1-r)*s,kc*r,1-kc*(b-(1-r)*s)),"Nc_CLT":math.pi*kc*kc/(2*.35**2*.6**2)}
# For y'=a*y+d*y^3, symmetric two-cycle y^2=-(a+1)/d.
rows["cubic_sign"]={"a":-1.1,"d_positive":1.,"cycle_sq_positive_d":.1,"d_negative":-1.,"cycle_sq_negative_d":-.1}
rows["single_verdict_noise"]={"at_e0_mean":0.,"at_e0_variance_any_odd_N":1.,"mean_abs_delta_theta_over_2":.35/2,"meaning":"A realised majority verdict has O(1), not O(N^-1/2), variance at zero."}
# Exact dictator weighted-majority counterexample.
rows["weighted_dictator"]={"weights":[.75,.25],"response_mean":"m","exact_derivative":1.,"invalid_claim_upper_bound":math.sqrt(2/math.pi)}
assert rows["constant_gain"][0]["stable"] and not rows["constant_gain"][2]["stable"]
assert not rows["negative_exponent"][0]["stable"] and rows["negative_exponent"][1]["stable"]
assert rows["anf_symmetric_cycle"]["one_step_to_negative_residual"]<1e-12
assert abs(rows["depth_exponent"]["Nc_correct"]/rows["depth_exponent"]["Nc_flat"]-2)<1e-12
out={"schema":"anf.reconciliation-algebra/1","author_origin":True,"independent_review":"PENDING","measures":{"cycle_residual":rows["anf_symmetric_cycle"]["one_step_to_negative_residual"],"depth_ratio":2.0,"odd_verdict_variance":1.0},"checks":rows,"limitations":["Small deterministic algebra checks only","No historical outputs overwritten or rerun","No full nonlinear global-attractor theorem","No empirical domain or transformer validation"]}
with open(args.result,"w",encoding="utf-8") as h: json.dump(out,h,indent=2,allow_nan=False)
print("Algebra counterexamples and conditional formula checks written. No scientific acceptance asserted.")
