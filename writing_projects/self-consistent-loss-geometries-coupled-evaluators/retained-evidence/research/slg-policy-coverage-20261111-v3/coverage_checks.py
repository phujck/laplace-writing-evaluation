"""Four policy calls closing V2-03/04. Execute the pinned v1 AST, not a rewritten selector."""
from __future__ import annotations
import argparse, ast, copy, hashlib, json, platform, sys
from fractions import Fraction as F
from pathlib import Path
import numpy as np

def sha(b): return hashlib.sha256(b).hexdigest()
def fraction_record(q):
    return dict(numerator=q.numerator,denominator=q.denominator,decimal=float(q))
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode",required=True); ap.add_argument("--args-json",required=True)
    ap.add_argument("--result",required=True); opt=ap.parse_args()
    assert opt.mode=="smoke" and json.loads(opt.args_json)=={}
    here=Path(__file__).resolve().parent; project=here.parents[1]
    cfg_bytes=(here/"parameters.json").read_bytes(); cfg=json.loads(cfg_bytes)
    source=(project/cfg["policy_source"]).read_bytes()
    params=(project/cfg["policy_parameters"]).read_bytes()
    assert sha(source)==cfg["policy_source_sha256"]
    assert sha(params)==cfg["policy_parameters_sha256"]
    action=json.loads(params)["action"]
    assert action["alpha"]==.22 and action["beta"]==2.5 and action["ridge_denominator"]==1e-6
    tree=ast.parse(source.decode()); oldmain=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main")
    loop=next(n for n in oldmain.body if isinstance(n,ast.For) and isinstance(n.iter,ast.Call)
        and isinstance(n.iter.func,ast.Name) and n.iter.func.id=="range"
        and len(n.iter.args)==2 and isinstance(n.iter.args[0],ast.Constant) and n.iter.args[0].value==1
        and isinstance(n.iter.args[1],ast.Name) and n.iter.args[1].id=="n")
    start=next(i for i,n in enumerate(loop.body) if isinstance(n,ast.Assign)
        and isinstance(n.value,ast.Name) and n.value.id=="state1")
    policy_nodes=copy.deepcopy(loop.body[start:])
    assert isinstance(policy_nodes[-1],ast.Expr) and isinstance(policy_nodes[-1].value,ast.Call)
    assert isinstance(policy_nodes[-1].value.func,ast.Attribute)
    assert policy_nodes[-1].value.func.attr=="append"
    assert policy_nodes[-1].value.func.value.id=="v1_rows"
    mse_node=copy.deepcopy(next(n for n in oldmain.body if isinstance(n,ast.FunctionDef) and n.name=="mse"))
    policy_ast=ast.Module(body=policy_nodes,type_ignores=[])
    policy_code=compile(policy_ast,"<unchanged-pinned-v2-v1-policy>","exec")
    mse_code=compile(ast.Module(body=[mse_node],type_ignores=[]),"<unchanged-pinned-v2-mse>","exec")
    assert ast.dump(policy_ast,include_attributes=False)==ast.dump(ast.Module(body=loop.body[start:],type_ignores=[]),include_attributes=False)
    source_lines=source.decode().splitlines()
    policy_text="\n".join(source_lines[policy_nodes[0].lineno-1:policy_nodes[-1].end_lineno])+"\n"
    tests=[]; rows=[]; call_counter=0; tolerance=cfg["tolerance_abs"]
    def numeric(name,observed,expected):
        error=abs(float(observed)-float(expected))
        tests.append(dict(name=name,kind="numeric_oracle",observed=float(observed),expected=float(expected),
                          abs_error=error,tolerance=tolerance,passed=bool(error<=tolerance)))
    def exact(name,condition,detail):
        tests.append(dict(name=name,kind="exact_execution",passed=bool(condition),detail=detail))
    def new_env():
        env={"np":np,"alpha":action["alpha"],"beta":action["beta"],"ridge":action["ridge_denominator"],
             "state1":1.,"predicted_applied":[],"measured_equal":[],"no_update_g":[],"v1_rows":[]}
        exec(mse_code,env)
        return env
    def oracle(theta,n,price,expected_action):
        # No numpy MSE or policy comparison here: independent exact scalar polynomial oracle.
        target=F(n)*F(4,5)/(F(n)+F(1,1000000))
        candidate=theta+F(11,50)*(target-theta)
        delta=candidate-theta
        gain=2*delta*(F(4,5)-theta)-delta*delta
        return dict(theta_before=theta,fit=target,candidate0=theta,candidate1=candidate,
                    gain0=F(0),gain1=gain,score0=F(0),score1=F(5,2)*gain-price,
                    chosen=expected_action,theta_after=candidate if expected_action else theta,
                    realised_gain=gain if expected_action else F(0),cost0=F(0),cost1=price)
    def invoke(fixture_id,env,n,price,expected,carried_from=None):
        nonlocal call_counter
        env["n"]=n; env["xx"]=np.ones(n); env["yy"]=np.full(n,.8); env["t"]=n-1
        start_idx=max(0,env["t"]-action["window"]+1)
        env["xw"]=env["xx"][start_idx:env["t"]+1]; env["yw"]=env["yy"][start_idx:env["t"]+1]
        env["a"]={**action,"costs":[0.,float(price)]}
        before=float(env["state1"]); len_before=len(env["v1_rows"])
        exec(policy_code,env)  # SAME selection AND application path for promote, carry, stay, tie.
        call_counter+=1
        exact(fixture_id+"_actual_policy_append",len(env["v1_rows"])==len_before+1,"Original v1_rows.append executed.")
        observed=dict(env["v1_rows"][-1]); selected=int(observed["chosen"])
        exact(fixture_id+"_action",selected==expected["chosen"],"Expected action declared by rational oracle/fixture, not inferred from test difference.")
        numeric(fixture_id+"_starting_state",observed["theta_before"],expected["theta_before"])
        numeric(fixture_id+"_candidate0",observed["theta0"],expected["candidate0"])
        numeric(fixture_id+"_candidate1",observed["theta1"],expected["candidate1"])
        numeric(fixture_id+"_gain0",observed["gain0"],expected["gain0"])
        numeric(fixture_id+"_gain1_polynomial",observed["gain1"],expected["gain1"])
        numeric(fixture_id+"_ending_state",env["state1"],expected["theta_after"])
        numeric(fixture_id+"_realised_gain",observed["realised_window_gain"],expected["realised_gain"])
        numeric(fixture_id+"_score0",observed["score0"],expected["score0"])
        numeric(fixture_id+"_score1",observed["score1"],expected["score1"])
        exact(fixture_id+"_applied_state_record",env["state1"]==observed["theta_after"],"Recorded row and actual persistent state agree.")
        if selected==1:
            exact(fixture_id+"_actual_nonzero_update",env["state1"]!=before,"A chosen partial update actually changed persistent state.")
        else:
            exact(fixture_id+"_actual_stay",env["state1"]==before,"Chosen no-update preserved persistent state.")
        if carried_from is not None:
            exact(fixture_id+"_actual_carry",before==carried_from,"Same mutable execution environment retains previous actual updated state.")
            exact(fixture_id+"_not_reset",before!=1.,"Carried state is not the original initial state.")
        rows.append(dict(fixture=fixture_id,policy_call=call_counter,scoring_horizon=dict(index_start=start_idx,
            index_end=env["t"],n=n,objective="mean (y_i-theta*x_i)^2 on this same available window"),
            x=env["xx"].tolist(),y=env["yy"].tolist(),costs=env["a"]["costs"],starting_state=before,
            ending_state=float(env["state1"]),actual_policy_row=observed,carried_from_actual=carried_from,
            oracle={k:fraction_record(v) if isinstance(v,F) else v for k,v in expected.items()},
            exact_score_tie=observed["score0"]==observed["score1"],
            binary64=dict(score0=float(observed["score0"]).hex(),score1=float(observed["score1"]).hex(),
                          cost1=float(price).hex(),gain1=float(observed["gain1"]).hex())))
        return observed
    initial=F(1)
    chain=new_env()
    first_oracle=oracle(initial,8,F(1,50),1)
    promoted=invoke("promote",chain,8,.02,first_oracle)
    carried=float(chain["state1"])
    # No state assignment/reset between these calls. Only the new observation window and time advance.
    carry_oracle=oracle(first_oracle["theta_after"],9,F(1,50),1)
    invoke("carried_next",chain,9,.02,carry_oracle,carried_from=carried)
    invoke("stay",new_env(),8,.06,oracle(initial,8,F(3,50),0))
    # Construct a finite-price tie from the identical scored candidate already observed in promote.
    # Then invoke the FULL original policy with that price, rather than testing a literal 0>0.
    tie_price=action["beta"]*(promoted["gain1"]-promoted["gain0"])
    tie_algebra=F(5,2)*first_oracle["gain1"]
    tied=invoke("tie",new_env(),8,tie_price,oracle(initial,8,tie_algebra,0))
    exact("tie_scores_equal_in_actual_policy",tied["score0"]==tied["score1"],"Strict original policy saw exactly equal binary scores. No epsilon used.")
    exact("tie_price_positive",tie_price>0,"Tie is between a beneficial partial update and its positive price, not an empty placeholder.")
    counts=dict(policy_calls=call_counter,promoted=sum(r["actual_policy_row"]["chosen"]==1 for r in rows),
        stay=sum(r["actual_policy_row"]["chosen"]==0 for r in rows),
        tie_calls=sum(r["exact_score_tie"] for r in rows),
        carried_transition_calls=sum(r["carried_from_actual"] is not None for r in rows))
    for key,value in cfg["expected_counts"].items():
        exact("coverage_count_"+key,counts[key]==value,dict(observed=counts[key],expected=value))
    failed=[t for t in tests if not t["passed"]]
    out=dict(schema_version="slg.policy-coverage-result/3",status="PASSED" if not failed else "FAILED",
        work_id=cfg["work_id"],scope=cfg["limits"],counts=counts,tests=tests,rows=rows,
        measures=dict(check_count=len(tests),failed_count=len(failed),**counts),
        extraction=dict(source_path=cfg["policy_source"],source_sha256=sha(source),
            line_start=policy_nodes[0].lineno,line_end=policy_nodes[-1].end_lineno,
            ast_unchanged=True,ast_sha256=sha(ast.dump(policy_ast,include_attributes=False).encode()),
            policy_text=policy_text,same_compiled_object_for_all_calls=True,
            mse_source=ast.get_source_segment(source.decode(),mse_node),original_main_executed=False),
        environment=dict(python=sys.version,numpy=np.__version__,platform=platform.platform(),executable=sys.executable,
            code_sha256=sha(Path(__file__).read_bytes()),protocol_sha256=sha(cfg_bytes),
            v2_parameters_sha256=sha(params)),
        interpretation="Four full policy calls exercise promoted, stay, positive-price exact binary tie and subsequent carried updated state. Numerical scalar-oracle comparisons use declared tolerance. No v0 or other v2 analytic reruns, no grid, no independent proof.")
    result=Path(opt.result); assert result.is_absolute()
    result.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    print(json.dumps(out["measures"]))
    if failed: raise SystemExit(1)
if __name__=="__main__": main()
