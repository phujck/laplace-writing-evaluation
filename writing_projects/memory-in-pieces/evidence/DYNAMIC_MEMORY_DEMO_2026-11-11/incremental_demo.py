"""Controlled exact update fixture. Standard library only. No Main imports/network/model calls."""
from __future__ import annotations
import argparse, collections, dataclasses, hashlib, json, math, pathlib, re, resource, sys, time, tracemalloc
from fractions import Fraction as F
BASE=pathlib.Path(__file__).resolve().parent
MAX=(1<<63)-1
LIMIT=128*1024*1024
GRAMMAR=re.compile(r"Group (\d{2}) contains ([1-9]\d*) records with A=([01]) and B=([01])\.\n?\Z")
def digest(x): return hashlib.sha256(x).hexdigest()
def encoded(x): return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def parse_incremental(v,stats):
    start=time.perf_counter_ns()
    data=(BASE/v["path"]).read_bytes()
    stats["input_bytes_read"]+=len(data); stats["source_documents_read"]+=1
    assert digest(data)==v["sha256"]
    text=data.decode("ascii")
    m=GRAMMAR.fullmatch(text)
    if not m or "d"+m[1]!=v["id"]: raise ValueError("grammar/group identity")
    weight=int(m[2])
    if weight>MAX: raise OverflowError("int64-compatible weight")
    stats["source_documents_parsed"]+=1
    stats["input_read_hash_parse_ns"]+=time.perf_counter_ns()-start
    return dict(id=v["id"],revision=v["revision"],path=v["path"],sha256=v["sha256"],
                text=text,weight=weight,key=(int(m[3]),int(m[4])),
                witness=[0,len(text.rstrip("\n"))],count_span=[m.start(2),m.end(2)])
@dataclasses.dataclass(frozen=True)
class Node:
    cut:int
    total:int
    children:tuple
    sid:int
class Pool:
    def __init__(self):
        self.index={};self.states={};self.refs=collections.Counter();self.live=[0,0,0]
    def intern(self,cut,edges,m):
        key=(cut,edges);m["hashcons_probes"]+=1
        if key not in self.index:
            sid=len(self.index);self.index[key]=sid;self.states[sid]=key;m["canonical_states_created"]+=1
        else:
            sid=self.index[key];m["canonical_states_reused"]+=1
        return sid
    def ref(self,sid,delta,m):
        old=self.refs[sid];new=old+delta
        assert new>=0
        cut=self.states[sid][0]
        if old==0 and new>0:self.live[cut]+=1
        if old>0 and new==0:self.live[cut]-=1
        self.refs[sid]=new;m["active_refcount_updates"]+=1
class Engine:
    """One raw prefix trie plus hash-consed exact conditional continuation states."""
    def __init__(self,queries):
        self.pool=Pool();self.root=None;self.docs={};self.counts={}
        self.active_messages={};self.canonical_messages={};self.queries=queries
    def invalidate(self,prefix,m):
        # Only the explicitly affected ancestor dependency key, not all source/quotient nodes.
        for qi in range(len(self.queries)):
            if (prefix,qi) in self.active_messages:
                del self.active_messages[prefix,qi];m["query_messages_invalidated"]+=1
    def path_delta(self,node,key,delta,cut,prefix,m):
        self.invalidate(prefix,m);m["prefixes_touched"]+=1
        old=node
        if cut==2:
            total=(node.total if node else 0)+delta
            if total<0:raise ValueError("negative tuple count")
            children=()
        else:
            children=dict(node.children) if node else {}
            m["child_pointer_slots_copied"]+=len(children)
            x=key[cut]
            child=self.path_delta(children.get(x),key,delta,cut+1,prefix+(x,),m)
            if child:children[x]=child
            else:children.pop(x,None)
            total=sum(c.total for c in children.values())
            m["transition_slots_examined"]+=len(children)
            children=tuple(sorted(children.items()))
        if total>MAX:raise OverflowError("int64-compatible total")
        if total:
            edges=tuple((x,F(c.total,total),c.sid) for x,c in children)
            sid=self.pool.intern(cut,edges,m)
            self.pool.ref(sid,1,m)
            node=Node(cut,total,children,sid);m["raw_nodes_path_copied"]+=1
        else:
            node=None;m["raw_nodes_removed"]+=bool(old)
        if old:self.pool.ref(old.sid,-1,m)
        return node
    def change(self,event,versions):
        m=collections.Counter();start=time.perf_counter_ns()
        before=list(self.pool.live);old=None;new=None;noop=False
        if event["op"]=="set":
            v=versions[event["version"]];old=self.docs.get(v["id"])
            # Replayed source content is still read/hashed; no reparsing or count retraction.
            if old and old["revision"]==v["revision"] and old["sha256"]==v["sha256"]:
                data=(BASE/v["path"]).read_bytes()
                assert digest(data)==v["sha256"]
                m["source_documents_read"]+=1;m["input_bytes_read"]+=len(data)
                m["idempotent_replay"]+=1;noop=True;new=old
            else:new=parse_incremental(v,m)
        else:old=self.docs[event["id"]]
        if not noop:
            total=(self.root.total if self.root else 0)-(old["weight"] if old else 0)+(new["weight"] if new else 0)
            if not 0<=total<=MAX:raise OverflowError("total overflow refused before mutation")
            deltas=collections.Counter()
            if old:
                deltas[old["key"]]-=old["weight"];m["facts_retracted"]+=1;m["incidence_edges_retracted"]+=1
            if new:
                deltas[new["key"]]+=new["weight"];m["facts_added"]+=1;m["incidence_edges_added"]+=1
            for key,delta in deltas.items():
                if not delta:continue
                updated=self.counts.get(key,0)+delta
                assert updated>=0
                m["tuple_entries_touched"]+=1
                if updated:self.counts[key]=updated
                else:self.counts.pop(key,None)
                self.root=self.path_delta(self.root,key,delta,0,(),m)
            if old:self.docs.pop(old["id"])
            if new:self.docs[new["id"]]=new
        m["algorithm_update_ns"]=time.perf_counter_ns()-start
        m["active_continuations_before"]=before[1]
        m["active_continuations_after"]=self.pool.live[1]
        def witness(d):
            return {k:d[k] for k in ("id","revision","path","sha256","text","weight","key","witness","count_span")} if d else None
        return dict(m),{"old":witness(old),"new":witness(new),"noop":noop}
    def message(self,node,prefix,qi,m):
        if node is None:return F(0)
        if node.cut==2:return F(1)
        k=(prefix,qi)
        if k in self.active_messages:
            m["active_message_hits"]+=1;return self.active_messages[k]
        factors=self.queries[qi]["factors"]
        ck=(node.sid,tuple(tuple(f) for f in factors[node.cut:]))
        if ck in self.canonical_messages:
            value=self.canonical_messages[ck];m["canonical_message_hits"]+=1
        elif any(all(x==0 for x in f) for f in factors[node.cut:]):
            value=F(0);m["zero_factor_shortcuts"]+=1
        elif all(all(x==1 for x in f) for f in factors[node.cut:]):
            value=F(1);m["ones_suffix_shortcuts"]+=1
        else:
            value=F(0);m["query_messages_recomputed"]+=1
            for x,child in node.children:
                m["query_dependency_edges_visited"]+=1
                value+=F(child.total,node.total)*factors[node.cut][x]*self.message(child,prefix+(x,),qi,m)
        self.canonical_messages[ck]=value;self.active_messages[k]=value
        return value
    def forward(self,factors):
        if not self.root:return F(0)
        state={self.root.sid:F(1)}
        for g in range(2):
            nxt=collections.defaultdict(F)
            for sid,mass in state.items():
                cut,edges=self.pool.states[sid];assert cut==g
                assert sum((p for _,p,_ in edges),F(0))==1
                assert sum((p*factors[g][x] for x,p,_ in edges),F(0))<=1
                for x,p,target in edges:nxt[target]+=mass*p*factors[g][x]
            state=nxt
        return sum(state.values(),F(0))
def parse_oracle(text,id):
    """Fresh token-position parser: independent of incremental regex/incidence."""
    z=text.strip().split()
    assert len(z)==9 and z[0]=="Group" and z[2]=="contains" and z[4:6]==["records","with"] and z[7]=="and"
    assert "d"+z[1]==id and z[6] in ("A=0","A=1") and z[8] in ("B=0.","B=1.")
    w=int(z[3]);assert 0<w<=MAX
    return (int(z[6][-1]),int(z[8][-2])),w
def parse_direct(text):
    """Third independent grammar path for direct row-sum oracle."""
    _,tail=text.strip().split(" contains ")
    w,tail=tail.split(" records with ")
    a,b=tail.rstrip(".").split(" and ")
    return (int(a.split("=")[1]),int(b.split("=")[1])),int(w)
def oracle_tree(rows,prefix=()):
    subset=[(key,w) for key,w in rows if key[:len(prefix)]==prefix]
    total=sum(w for _,w in subset)
    if not total:return None
    # Suffix-law canonicalisation from full observed rows, not from incremental state IDs/signature code.
    acc=collections.Counter()
    for key,w in subset:acc[key[len(prefix):]]+=w
    law=tuple(sorted((suffix,F(w,total)) for suffix,w in acc.items()))
    children={}
    if len(prefix)<2:
        for x in sorted({key[len(prefix)] for key,_ in subset}):
            children[x]=oracle_tree(rows,prefix+(x,))
    return {"prefix":prefix,"total":total,"law":law,"children":children}
def oracle_expect(tree,factors):
    if tree is None:return F(0)
    cut=len(tree["prefix"])
    if cut==2:return F(1)
    return sum((F(c["total"],tree["total"])*factors[cut][x]*oracle_expect(c,factors)
                for x,c in tree["children"].items()),F(0))
def node_law(node):
    if node.cut==2:return (((),F(1)),)
    out=[]
    for x,c in node.children:
        out.extend(((x,)+s,F(c.total,node.total)*p) for s,p in node_law(c))
    return tuple(sorted(out))
def validate(engine,versions):
    """Charged FULL oracle/verification scan; never called inside change()."""
    rows=[];direct=[];expected_witness=[]
    for id,d in sorted(engine.docs.items()):
        data=(BASE/d["path"]).read_bytes();text=data.decode("ascii")
        assert digest(data)==d["sha256"]
        k,w=parse_oracle(text,id);rows.append((k,w));direct.append(parse_direct(text))
        assert k==d["key"] and w==d["weight"]
        s,e=d["witness"];assert data[s:e].decode()==text.rstrip("\n")
        cs,ce=d["count_span"];assert int(data[cs:ce])==w
        expected_witness.append((id,d["revision"],d["sha256"],s,e,k,w))
    expected_counts=collections.Counter()
    for k,w in rows:expected_counts[k]+=w
    assert dict(expected_counts)==engine.counts
    tree=oracle_tree(rows)
    active=collections.Counter();groups=collections.defaultdict(list);law_count=0
    def walk(node,other,prefix):
        nonlocal law_count
        if node is None:assert other is None;return
        assert node.total==other["total"] and node_law(node)==other["law"]
        active[node.sid]+=1;groups[(node.cut,node_law(node))].append(prefix);law_count+=1
        for x,c in node.children:walk(c,other["children"][x],prefix+(x,))
    walk(engine.root,tree,())
    assert active==+engine.pool.refs
    entries=[];qm=collections.Counter();t=time.perf_counter_ns()
    for qi,q in enumerate(engine.queries):
        backward=engine.message(engine.root,(),qi,qm)
        forward=engine.forward(q["factors"])
        full=oracle_expect(tree,q["factors"])
        direct_count=sum(w*q["factors"][0][k[0]]*q["factors"][1][k[1]] for k,w in direct)
        W=sum(w for _,w in direct)
        assert backward==forward==full==F(direct_count,W)
        mass=backward*W;assert mass.denominator==1
        entries.append({"id":q["id"],"count":mass.numerator,"probability":str(backward)})
    qm["query_validation_ns"]=time.perf_counter_ns()-t
    num=next(x["count"] for x in entries if x["id"]=="A-zero__B-zero")
    den=next(x["count"] for x in entries if x["id"]=="A-zero__B-any")
    conditional=str(F(num,den)) if den else "UNDEFINED"
    shared=[{"cut":cut,"prefixes":ps,"law":[[s,str(p)] for s,p in law]} for (cut,law),ps in groups.items() if len(ps)>1]
    return {"query_results":entries,"conditional":{"query":"P(B=0 | A=0)","numerator":num,"denominator":den,"value":conditional},
            "source_witnesses":expected_witness,"tuple_counts":[{"A":k[0],"B":k[1],"count":w} for k,w in sorted(expected_counts.items())],
            "prefix_laws_verified":law_count,"shared_continuations":shared,"query_work":dict(qm),
            "oracle_full_documents_parsed":len(rows),"oracle_full_prefix_nodes":law_count,
            "oracle_assertions":"exact full rebuild == direct integer/Fraction rows == incremental adjoint == forward channel"}
def outer(v):return [[a*b for b in v] for a in v]
def plus(a,b):return [[a[i][j]+b[i][j] for j in range(2)] for i in range(2)]
def rowmul(v,m):return [sum(v[k]*m[k][j] for k in range(2)) for j in range(2)]
def matvec(m,v):return [sum(m[i][k]*v[k] for k in range(2)) for i in range(2)]
def defect(a,b):return max(abs(a[i][j]-b[i][j]) for i in range(2) for j in range(2))
def channel_fixture():
    tol=1e-12;I=[[1.,0.],[0.,1.]]
    a0=[math.sqrt(.8),math.sqrt(.2)];a1=[math.sqrt(.2),math.sqrt(.8)]
    Z=plus(outer(a0),outer(a1))
    assert defect(Z,[[1.,.8],[.8,1.]])<tol
    up,um=1/math.sqrt(1.8),1/math.sqrt(.2)
    inv=[[.5*(up+um),.5*(up-um)],[.5*(up-um),.5*(up+um)]]
    up,um=math.sqrt(1.8),math.sqrt(.2)
    sq=[[.5*(up+um),.5*(up-um)],[.5*(up-um),.5*(up+um)]]
    b0,b1=rowmul(a0,inv),rowmul(a1,inv)
    completion=plus(outer(b0),outer(b1))
    assert defect(completion,I)<tol
    first=[matvec(sq,[math.sqrt(.5),0]),matvec(sq,[0,math.sqrt(.5)])]
    assert abs(sum(sum(x*x for x in v) for v in first)-1)<tol
    joint=[[sum(b[k]*first[a][k] for k in range(2))**2 for b in (b0,b1)] for a in range(2)]
    expected=[[.4,.1],[.1,.4]]
    assert defect(joint,expected)<tol
    selected=outer(b0)
    R=[[I[i][j]-selected[i][j] for j in range(2)] for i in range(2)]
    assert R[0][0]>=-tol and R[1][1]>=-tol and R[0][0]*R[1][1]-R[0][1]*R[1][0]>=-tol
    # Singular prequotient environment: completeness is support projector, not I on null direction.
    invsing=[[1/(2*math.sqrt(2))]*2 for _ in range(2)]
    b=rowmul([math.sqrt(.5),math.sqrt(.5)],invsing)
    supported=plus(outer(b),outer(b));P=[[.5,.5],[.5,.5]]
    assert defect(supported,P)<tol
    return {"tolerance":tol,"naive_raw_completeness":Z,"naive_identity_defect":defect(Z,I),
            "gauged_completeness":completion,"gauged_identity_defect":defect(completion,I),
            "gauged_joint":joint,"gauged_joint_defect":defect(joint,expected),
            "singular_support_completeness":supported,"singular_support_defect":defect(supported,P),
            "domain":"Auxiliary finite instrument on environment support. Nonlinear positive-trace normalisation. No generic physical CP/Markov or time interpretation.",
            "signed_factors":"Remain observable contractions, not positive TNI instruments."}
def deep_size(obj):
    seen=set()
    def f(x):
        k=id(x)
        if k in seen:return 0
        seen.add(k);s=sys.getsizeof(x)
        if dataclasses.is_dataclass(x):return s+sum(f(getattr(x,z.name)) for z in dataclasses.fields(x))
        if isinstance(x,F):return s+f(x.numerator)+f(x.denominator)
        if isinstance(x,dict):return s+sum(f(k)+f(v) for k,v in x.items())
        if isinstance(x,(tuple,list,set)):return s+sum(f(v) for v in x)
        if hasattr(x,"__dict__"):return s+f(vars(x))
        return s
    return f(obj)
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--mode");ap.add_argument("--args-json");ap.add_argument("--result");args=ap.parse_args()
    assert args.mode=="smoke" and json.loads(args.args_json)=={}
    resource.setrlimit(resource.RLIMIT_CPU,(60,60))
    resource.setrlimit(resource.RLIMIT_AS,(LIMIT,LIMIT))
    wall=time.perf_counter_ns();cpu=time.process_time_ns();tracemalloc.start()
    spec=json.loads((BASE/"input.json").read_text())
    assert len(spec["queries"])==16 and len(spec["events"])==8
    e=Engine(spec["queries"]);states=[];init_metrics=collections.Counter()
    for ver in spec["initial"]:
        metrics,_=e.change({"op":"set","version":ver},spec["versions"]);init_metrics.update(metrics)
    events=[{"label":"initial","expected_conditional":spec["initial_expected_conditional"]}]+spec["events"]
    for ix,event in enumerate(events):
        if ix:
            oldroot=e.root;oldlaw=node_law(oldroot)
            metrics,delta=e.change(event,spec["versions"])
            assert node_law(oldroot)==oldlaw
        else:metrics=dict(init_metrics);delta={"initial_versions":spec["initial"]}
        t=time.perf_counter_ns();checked=validate(e,spec["versions"]);oracle_ns=time.perf_counter_ns()-t
        assert checked["conditional"]["value"]==event["expected_conditional"],(event,checked["conditional"])
        if event["label"]=="merge-continuations":assert e.pool.live[1]==1
        if event["label"]=="split-continuations":assert e.pool.live[1]==2
        if event["label"]=="idempotent-replay":
            assert metrics.get("raw_nodes_path_copied",0)==0 and metrics.get("source_documents_parsed",0)==0
        retained=deep_size(e);current,peak=tracemalloc.get_traced_memory();assert retained<LIMIT
        t=time.perf_counter_ns()
        active_docs=[dict(d) for _,d in sorted(e.docs.items())]
        states.append({"step":ix,"label":event["label"],"delta":delta,"active_documents":active_docs,
                       "algorithm_work":metrics,"oracle_and_query_validation_ns":oracle_ns,
                       "checks":checked,"algorithm_retained_bytes":retained,"tracemalloc_current_bytes":current,
                       "tracemalloc_peak_bytes":peak,"active_quotient_state_counts":list(e.pool.live),
                       "archived_canonical_states":len(e.pool.states)})
        states[-1]["snapshot_materialisation_ns"]=time.perf_counter_ns()-t
    rejection_specs=json.loads((BASE/"rejection-input.json").read_text())
    rejections=[]
    for label,v in rejection_specs.items():
        before=(e.root,dict(e.counts),dict(e.docs),node_law(e.root))
        t=time.perf_counter_ns()
        try:
            e.change({"op":"set","version":label},{label:v})
        except (OverflowError,ValueError) as error:
            assert e.root is before[0] and e.counts==before[1] and e.docs==before[2] and node_law(e.root)==before[3]
            rejections.append({"label":label,"error_type":type(error).__name__,"error":str(error),
                               "unchanged":True,"attempt_ns":time.perf_counter_ns()-t,
                               "input_source":v,"input_bytes":(BASE/v["path"]).stat().st_size,
                               "prefixes_nodes_touched":0,"admitted":False})
        else:raise AssertionError("invalid edit was accepted")
    fixture=channel_fixture()
    _,peak=tracemalloc.get_traced_memory()
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    assert rss<=LIMIT,(rss,LIMIT)
    output={"schema_version":"dynamic-memory.witnessed-incremental-demo/1","status":"PASSED_LOCAL_CHECKS_NOT_INDEPENDENT_ACCEPTANCE",
            "states":states,"rejected_edits":rejections,"channel_fixture":fixture,"query_count":16,"state_count":len(states),"changes":8,
            "input_sha256":digest((BASE/"input.json").read_bytes()),"code_sha256":digest(pathlib.Path(__file__).read_bytes()),
            "resources":{"wall_ns_before_output":time.perf_counter_ns()-wall,"CPU_ns_before_output":time.process_time_ns()-cpu,
                         "peak_RSS_bytes":rss,"tracemalloc_peak_bytes":peak,"address_space_hard_limit_bytes":resource.getrlimit(resource.RLIMIT_AS)[1],
                         "CPU_hard_limit_seconds":resource.getrlimit(resource.RLIMIT_CPU)[1],"strict_RSS_guard":"NOT_CLAIMED; observed RSS assertion plus RLIMIT_AS",
                         "supervisor_render_overhead":"Separate, not included in producer ru_maxrss; not measured here."},
            "limits":{"formal":"NOT_CHECKED","model_network_calls":0,"continuous_fixture":"NOT_RUN","larger_replicas":"NOT_RUN",
                      "claim_scope":"Fixed A,B order, binary factors, <=5 controlled weighted-source groups. No universal update complexity or application performance claim.",
                      "algorithm":"New stdlib path-copy/count/hash-cons/refcount/message cache fixture; original GPU snapshot/full-build code not modified or executed.",
                      "retention":"Canonical immutable signatures and messages archived; charged retained storage, no hidden global rebuild in change().",
                      "cost_separation":"Incremental update work excludes charged full-rebuild/direct oracle and output materialisation. Query work includes exact forward/adjoint comparison in validation."}}
    start=time.perf_counter_ns();blob=json.dumps(output,indent=2,ensure_ascii=False);output["resources"]["first_JSON_serialization_ns"]=time.perf_counter_ns()-start
    output["resources"]["final_write_measurement"]="Second serialization/file write not timed internally; native run covers whole process."
    pathlib.Path(args.result).write_text(json.dumps(output,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"states":len(states),"queries":16,"fractions":[s["checks"]["conditional"]["value"] for s in states],"peak_RSS_bytes":rss}))
if __name__=="__main__":main()
