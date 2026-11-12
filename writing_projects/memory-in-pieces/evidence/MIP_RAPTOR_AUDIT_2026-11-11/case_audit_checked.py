"""Deterministic diagnostic replay of stored selections. No inference or scoring."""
import argparse,json,time,resource
from pathlib import Path
def packing(order, turns, budget):
    selected=[]; used=0; visited=0; skipped=[]
    for pos,i in enumerate(order,1):
        visited=pos
        cost=turns[str(i)]["tokens"]+12
        if used+cost<=budget:
            selected.append(i); used+=cost
            if len(selected)>=120: break
        else: skipped.append({"local":i,"rank":pos,"cost":cost,"remaining":budget-used})
        if budget-used<30: break
    return {"selected":selected,"used_tokens_with_header_allowance":used,"remaining":budget-used,
            "last_visited_rank":visited,"skipped":skipped}
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--mode",required=True);ap.add_argument("--args-json",required=True);ap.add_argument("--result",required=True);a=ap.parse_args()
    assert a.mode=="smoke" and json.loads(a.args_json)=={}
    resource.setrlimit(resource.RLIMIT_CPU,(10,10));resource.setrlimit(resource.RLIMIT_AS,(128*1024**2,128*1024**2))
    start=time.monotonic(); cpu=time.process_time()
    d=json.loads(Path(__file__).with_name("case-audit-input.json").read_text());lm=d["longmem"];cells={}
    id_local={t["id"]:int(i) for i,t in lm["turns"].items()}
    for arm,order in lm["orders"].items():
        for budget in (4000,8000):
            key=f"{arm}@{budget}";p=packing(order,lm["turns"],budget)
            p["matches_stored_selection"]=(p["selected"]==lm["selections"][key])
            assert p["matches_stored_selection"],key
            p["required_trace"]=[{"id":rid,"local":id_local[rid],"rank":order.index(id_local[rid])+1 if id_local[rid] in order else None,
                "visited":id_local[rid] in order[:p["last_visited_rank"]],"delivered":id_local[rid] in p["selected"]} for rid in lm["required_turn_ids"]]
            p["accepted_answer"]=lm["accepted_rows"][lm["qid"]+"|"+key]["answer"];p["accepted_correct"]=lm["accepted_rows"][lm["qid"]+"|"+key]["correct"]
            cells[key]=p
    news=d["news"]["misses"];assert len(news)==20
    ng={"all_needed_spans_delivered":0,"some_needed_spans_missing":0,"exact_match_miss_containment_proxy_true":0}
    for r in news:
        ng["all_needed_spans_delivered" if r["diag_covered"] and all(r["diag_covered"]) else "some_needed_spans_missing"]+=1
        ng["exact_match_miss_containment_proxy_true"]+=bool(r["accepted_outcome"]["cont"])
    fc={};wrong=[];proxy=[]
    for r in d["frames"]["cases"]:
        if r["accepted_answer"]["cont"] is False:proxy.append(r["qid"])
        if r["judged"] is not False:continue
        x=r["delivery"]
        stage=("delivery_unobserved" if x is None else "linked_page_delivery_gap" if not x[1] else
               "answer_string_passage_delivery_gap" if x[0] is False else "reference_string_delivered_rubric_wrong" if x[0] is True else
               "answer_bearing_support_unresolved")
        fc[stage]=fc.get(stage,0)+1;wrong.append({"qid":r["qid"],"stage_evidence":stage,**r})
    assert len(wrong)==63 and len(proxy)==67
    out={"schema_version":"mip.deterministic-miss-audit/1","kind":"diagnostic_no_rescoring","longmem":{"qid":lm["qid"],"cells":cells,
         "all_required_turn_cost":sum(lm["turns"][str(id_local[i])]["tokens"]+12 for i in lm["required_turn_ids"]),
         "same_relational_dense_order":lm["orders"]["ours_keys"]==lm["orders"]["dense_keys"]},
         "news":{"miss_count":len(news),"groups":ng,"rows":news},
         "frames":{"judged_miss_count":len(wrong),"proxy_miss_count":len(proxy),"stage_evidence_counts":fc,"judged_misses":wrong,"proxy_miss_qids":proxy},
         "limits":["No new score/judgement, causal experiment, ranking inference or full raw-source recomputation.",
                   "Delivered reference strings or linked pages do not prove semantic answer support.",
                   "Any gold-labelled turn costs are diagnosis only and never selector input."],
         "resources":{"wall_seconds":time.monotonic()-start,"cpu_seconds":time.process_time()-cpu,"maxrss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}}
    body=json.dumps(out,ensure_ascii=False,indent=2)
    assert len(body.encode())<256000
    Path(a.result).write_text(body+"\n")
if __name__=="__main__":main()
