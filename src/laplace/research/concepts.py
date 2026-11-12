"""Focused readable views over the existing corpus network and rewire ledger."""
from __future__ import annotations
from laplace.core.checkout import source_tree

from laplace.core import identity_doors
import hashlib, json
from pathlib import Path
from typing import Any

_JSON="application/json; charset=utf-8"

def _root(): return source_tree()
def _resp(s:int,x:Any): return s,_JSON,json.dumps(x,ensure_ascii=False,sort_keys=True).encode()
def _q(q:dict,k:str):
    x=q.get(k,""); return (x[0] if isinstance(x,(list,tuple)) and x else x).strip() if isinstance((x[0] if isinstance(x,(list,tuple)) and x else x),str) else ""
def _label(node:dict,nid:str): return node.get("label") or node.get("essence") or nid
def _short_title(node:dict):
    title=(node.get("projection") or {}).get("title") or node.get("title")
    return title if isinstance(title,str) and title.strip() else None

def _revision(nodes:dict,relations:list,rows:list) -> str:
    return hashlib.sha256(json.dumps({"rows":rows,"nodes":nodes,"relations":relations},
                                     sort_keys=True,default=str).encode()).hexdigest()

def _network(project:str, root:Path):
    from laplace.research import corpus_ingest as ci
    tex=ci.resolve_corpus(root,project)
    return ci.corpus_network(tex,repo_root=root,name=project) if tex else None

def _relations(project:str,root:Path,net:dict):
    from laplace.research import corpus_ingest as ci
    rows=ci.rewire_list(root,project)
    out=[]
    projected = net.get("relations")
    if projected is None:
        projected,_diagnostics=ci.relation_projection(
            net.get("nodes") or {},net.get("edge_index") or {},records=rows)
    for relation in projected or []:
        provenance=list(relation.get("provenance") or [])
        rel=relation.get("rel")
        direction=("requires" if rel=="prerequisite" else "evidence"
                   if rel in {"support","validated_by","implementation"} else
                   "counterevidence" if rel=="counterevidence" else
                   "question" if rel=="questions" else
                   "lateral" if rel=="analogy" else "unknown")
        out.append({key:relation.get(key) for key in
                    ("source","target","rel","axis","inferential","ambiguous","rationale")}
                   | {"provenance":provenance,
                      "direction":direction,"orientation":relation.get("direction"),
                      "diagnostics":list(relation.get("diagnostics") or []),
                      "reason":"; ".join(sorted({str(p.get('producer')) for p in provenance}))})
    return out,rows


def _content_revision(project: str, focus: str, data: dict, immediate: list[dict], root: Path,
                      mathematical_record: dict | None = None, nodes:dict|None=None, read_context=None) -> str:
    """One node's logical and source identity, independent of unrelated graph edits."""
    from laplace.research import mathematical_records
    def source_identities(node:dict,record:dict|None=None):
        raw = node.get("source") or node.get("sources") or node.get("ref") or []
        authored = ((node.get("projection") or {}).get("mathematics") or {}).get("sources") or []
        refs = ((raw if isinstance(raw,list) else [raw])
                + (authored if isinstance(authored,list) else [authored]))
        if isinstance(record,dict):
            resolved=record.get("source_locations") or []
        else:
            resolved=[mathematical_records.resolve_source(project,ref,root,read_context=read_context) for ref in refs[:6]]
        return [{key: row.get(key) for key in
                 ("reference","status","file","sha256","line_start","line_end","error")}
                for row in resolved if isinstance(row,dict)]
    sources=source_identities(data,mathematical_record)
    prerequisites=[]
    nodes=nodes or {}
    for relation in immediate:
        if relation.get("source")!=focus or relation.get("rel")!="prerequisite":continue
        target=str(relation.get("target") or "");target_data=nodes.get(target) or {}
        prerequisites.append({"node":target,"content":target_data,
                              "sources":source_identities(target_data)})
    return hashlib.sha256(json.dumps({"node": focus, "content": data,
                                      "relations": immediate, "sources": sources,
                                      "prerequisites":prerequisites},
                                     sort_keys=True, ensure_ascii=False, default=str,
                                     separators=(",", ":")).encode()).hexdigest()


def identity(project:str,node:str,root:Path|None=None,*,network_snapshot=None):
    """Small exact node identity for guards that do not render concept detail."""
    root=(root or _root()).resolve()
    if network_snapshot is None:
        net=_network(project,root)
        if not net:return None
        rels,rows=_relations(project,root,net)
    else:
        net,rels,rows=network_snapshot
    nodes=net.get("nodes") or {}
    if node not in nodes:return None
    data=nodes[node];immediate=[r for r in rels if r["source"]==node or r["target"]==node]
    mathematical_record=None
    from laplace.research import mathematical_records
    if data.get("kind") in mathematical_records.KINDS or (data.get("projection") or {}).get("mathematics"):
        mathematical_record=mathematical_records.read(
            project,node,data,root,include_verification=False)
    return {"id":node,"label":_label(data,node),"kind":data.get("kind"),
            "content_revision":_content_revision(
                project,node,data,immediate,root,mathematical_record,nodes)}

def state(project:str,node:str="",q:str="",root:Path|None=None,*,network_snapshot=None,read_context=None):
    root=(root or _root()).resolve()
    if network_snapshot is None:
        net=_network(project,root)
        if not net:return None
        rels,rows=_relations(project,root,net)
    else:
        net,rels,rows=network_snapshot
    if not net: return None
    nodes=net.get("nodes") or {}
    if node and node not in nodes:
        return None
    matches=[nid for nid,data in nodes.items() if q.lower() in (nid+" "+str(_label(data,nid))).lower()] if q else []
    focus=node or (matches[0] if matches else next(iter(nodes),"")); data=nodes.get(focus,{})
    immediate=[r for r in rels if r["source"]==focus or r["target"]==focus]
    neighbor_ids=list(dict.fromkeys(endpoint for r in immediate for endpoint in (r['source'],r['target']) if endpoint!=focus and endpoint in nodes))
    glossary=[{"id":nid,"term":(data.get("projection") or {}).get("term"),"label":_label(data,nid)} for nid,data in nodes.items() if data.get("kind") in {"definition","def"} or (data.get("projection") or {}).get("term")]
    revision=_revision(nodes,rels,rows)
    read_context={} if read_context is None else read_context
    mathematical_record = None
    from laplace.research import mathematical_records
    if data.get("kind") in mathematical_records.KINDS or (data.get("projection") or {}).get("mathematics"):
        mathematical_record = mathematical_records.read(project,focus,data,root,read_context=read_context)
    try:source_support=_source_support(project,focus,root,net,source_record=mathematical_record,read_context=read_context) if focus else None
    except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
        source_support={"node":focus,"sources":[],"own_evidence":[],"authored_proof":False,
            "gaps":[{"kind":"support-projection-unavailable","reason":str(exc)}],
            "qualification":"OPEN","independent_verification":"NOT_ASSERTED",
            "omission":{"associations_omitted":0,"citations_omitted":0}}
    content_revision=_content_revision(project, focus, data, immediate, root,
                                       mathematical_record,nodes,read_context=read_context)
    result = {"schema_version":"laplace.concepts/1","project":project,"revision":revision,
            # Every identity this read observed, under the name of its own home.  Two homes:
            # `concept-network` (the whole graph, the value `revision` carries) and
            # `concept-node` (this node's own content, the value `content_revision` carries).
            # `mutation_revision` is kept as a SHIM of `content_revision` -- byte-identical,
            # one of the twenty -- because static_shared/concept-reader.mjs:115 reads it off
            # this response and sends it as the guard; it expires with the rest of the shims
            # (identity_doors.EXPIRY) when the browser sends the token instead.
            # EVERY scalar identity name in this read -- `revision`, `content_revision` and
            # `mutation_revision` -- is a row of `identity_doors.RETAINED` carrying its home,
            # its live consumer, what deletes it and that same dated expiry.  A reader here
            # reaches a date, not only a condition.
            "identities":identity_doors.identities(
                ("concept-network",project,revision),
                ("concept-node","%s::%s"%(project,focus) if focus else "",content_revision)),
            "content_revision":content_revision,"mutation_revision":content_revision,
            "focus":{"id":focus,"title":_short_title(data),"label":_label(data,focus),"kind":data.get("kind"),"status":data.get('status'),"summary":data.get("essence",""),"projection":data.get("projection",{}),"source":data.get("source") or data.get("sources") or data.get("ref")},
            "relations":immediate,"search":[{"id":nid,"label":_label(nodes[nid],nid)} for nid in matches[:20]],
            "neighbors":[{"id":nid,"label":_label(nodes[nid],nid),"kind":nodes[nid].get('kind'),"status":nodes[nid].get('status')} for nid in neighbor_ids[:40]],
            "neighbors_omitted":max(0,len(neighbor_ids)-40),
            "relation_diagnostics":list(net.get("relation_diagnostics") or []),
            "source_support":source_support,
            "spine":net.get("spine",[]),"glossary":glossary[:30],"omitted":max(0,len(rels)-len(immediate))}
    if mathematical_record is not None:
        result["mathematical_record"] = mathematical_record
        result["source_locations"]=mathematical_record.get("source_locations") or []
    else:
        result["source_locations"]=[mathematical_records.resolve_source(project,ref,root,read_context=read_context) for ref in _source_refs(data)[:6]]
    engineering=(source_support or {}).get('engineering_support') or {}
    bindings=engineering.get('bindings') or []
    if bindings and all(row.get('adoption_permitted') for row in bindings):
        engineering['adoption_handle']={'operation':'concept_change',
            'payload':{'project':project,'operation':'set_projection','node':focus,'base_revision':revision,
                       'value':{'engineering_support':[row['adoption'] for row in bindings]}},
            'http':{'method':'POST','url':'/concepts/change'},
            'requires':'Inspect the exact current covered work/claim basis before explicit acknowledgement; this grants no independent verification.'}

    return result

def catalog(project:str, q:str="", offset:int=0, limit:int=80, root:Path|None=None):
    root=(root or _root()).resolve();net=_network(project,root)
    if not net:return None
    from laplace.research.corpus_ingest import DERIVATION_KINDS, LOGICAL_KINDS
    nodes=net.get('nodes') or {}
    rows=[]
    for ident,node in nodes.items():
        label=str(_label(node,ident))
        if q and q.casefold() not in (ident+' '+label).casefold():continue
        if not q and node.get('kind') not in set(LOGICAL_KINDS)|set(DERIVATION_KINDS):continue
        rows.append({'id':ident,'title':_short_title(node),'label':label.split('\n')[0][:180],
                     'kind':node.get('kind'),'status':node.get('status')})
    rows.sort(key=lambda row:(str(row['kind'] or ''),row['label'].casefold(),row['id']))
    limit=max(1,min(200,int(limit)));offset=max(0,int(offset));page=rows[offset:offset+limit]
    return {'schema_version':'laplace.concept-catalog/1','project':project,
            'revision':hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest(),
            'items':page,'total':len(rows),'offset':offset,
            'next_offset':offset+limit if offset+limit<len(rows) else None,
            'scope':'declared logical objects' if not q else 'matching project objects',
            'read_routes':{'item':{'operation':'concept','payload':{'node':'<item_id>'}},
                'attention':{'operation':'logical_plan','payload':{'node':'<item_id>'}},
                'tree':{'operation':'concept_tree','payload':{'node':'<item_id>'}}},
            **({'next_read':{'operation':'logical_plan','payload':{
                'view':'catalog','q':q,'offset':offset+limit,'limit':limit}}}
               if offset+limit<len(rows) else {})}


def tree_contract() -> dict:
    string={"type":"string"}
    return {"schema_version":"laplace.concept-tree-contract/1","type":"object",
        "required":["project"],"additionalProperties":False,
        "properties":{"project":{"type":"string","minLength":1},"node":string,
            "direction":{"enum":["current","down","up","dependency"]},"from":string,
            "offset":{"type":"integer","minimum":0},"limit":{"type":"integer","minimum":1,"maximum":100},
            "uncontained_offset":{"type":"integer","minimum":0},
            "dependency_offset":{"type":"integer","minimum":0},
            "dependency_limit":{"type":"integer","minimum":1,"maximum":200},
            "goal":{"type":"string","maxLength":2000}},
        "navigation":{"down":{"requires":["node","from"],"authority":"conceptric.children_view"},
            "up":{"requires":["node"],"authority":"conceptric.identity_chain",
                  "note":"node is the child; its current parent is re-derived when followed"},
            "dependency":{"requires":["node","from"],"authority":"canonical typed edge",
                          "conjugate_up":False}}}


def _tree_row(nodes:dict, ident:str) -> dict:
    node=nodes[ident]; summary=str(node.get("essence") or "")
    members=list(node.get("members") or [])
    return {"id":ident,"title":_short_title(node),"label":_label(node,ident),"kind":node.get("kind"),
            "status":node.get("status"),"summary":summary[:2000],
            "summary_truncated":len(summary)>2000,"grade":node.get("grade",0),
            "parent":node.get("parent"),"has_children":bool(members),
            "child_count":len(members),"source":node.get("source") or node.get("sources") or node.get("ref"),
            "projection":node.get("projection") or {}}

def _breadcrumb(nodes:dict,ident:str) -> dict:
    node=nodes[ident]
    return {"id":ident,"title":_short_title(node),"label":_label(node,ident),"kind":node.get("kind"),
            "grade":node.get("grade",0),"parent":node.get("parent")}


def tree(project:str,node:str="",offset:int=0,limit:int=40,uncontained_offset:int=0,
         dependency_offset:int=0,dependency_limit:int=80,root:Path|None=None,
         direction:str="current",from_node:str="",goal:str=""):
    """One bounded live grade view: canonical DOWN handles and re-derived identity UP."""
    root=(root or _root()).resolve(); net=_network(project,root)
    if not net:return None
    from laplace.engine import conceptric
    nodes=net.get("nodes") or {}; requested=node or str(net.get("root") or "")
    if requested not in nodes:return None
    rels,rows=_relations(project,root,net)
    revision=_revision(nodes,rels,rows)
    request={"direction":direction,"requested_node":requested,"from_node":from_node or None,
             "rederived_from_live_revision":revision}
    if direction=="up":
        requested_chain=conceptric.identity_chain(net,requested)
        focus=requested_chain[-1]["id"] if requested_chain else requested
        request.update(kind="containment-ascent",resolved_node=focus,
                       at_root=not bool(requested_chain),authority="conceptric.identity_chain")
    elif direction=="down":
        if not from_node or from_node not in nodes or nodes[requested].get("parent")!=from_node:
            raise ValueError("descent handle is stale or does not name a current direct child")
        focus=requested
        request.update(kind="containment-descent",resolved_node=focus,
                       authority="conceptric.children_view")
    elif direction=="dependency":
        if not from_node or from_node not in nodes or not any(
                {edge.get("source"),edge.get("target")}=={from_node,requested} for edge in rels):
            raise ValueError("dependency handle is stale or does not name a current typed relation")
        focus=requested
        request.update(kind="typed-dependency-follow",resolved_node=focus,
                       authority="canonical typed edge",conjugate_up=False)
    elif direction=="current":
        focus=requested;request.update(kind="open",resolved_node=focus,
                                       authority="corpus_ingest.corpus_network")
    else:
        raise ValueError("direction must be current, down, up, or dependency")
    offset=int(offset);limit=int(limit);uncontained_offset=int(uncontained_offset);dependency_offset=int(dependency_offset);dependency_limit=int(dependency_limit)
    if offset<0 or uncontained_offset<0 or dependency_offset<0:
        raise ValueError("concept_tree offsets must be non-negative")
    if limit<1 or limit>100 or dependency_limit<1 or dependency_limit>200:
        raise ValueError("concept_tree limits are outside the declared bounds")
    canonical_children=[handle for handle in conceptric.children_view(net,focus)
                        if handle.get("id") in nodes and nodes[handle["id"]].get("parent")==focus]
    child_ids=[handle["id"] for handle in canonical_children]
    child_handles={handle["id"]:handle for handle in canonical_children}
    page_ids=child_ids[offset:offset+limit]
    identity=conceptric.identity_chain(net,focus)
    ancestors=[{**_breadcrumb(nodes,link["id"]),"share":link["share"]}
               for link in identity[-100:] if link["id"] in nodes]
    ancestors_omitted=max(0,len(identity)-len(ancestors));hierarchy_gaps=[]
    raw_parent=nodes[focus].get("parent")
    if raw_parent and (not identity or identity[-1]["id"]!=raw_parent):
        hierarchy_gaps.append({"kind":"unresolved-uplink","id":str(raw_parent),
                               "reason":"identity_chain refused a dangling or cyclic parent"})
    scope=set(child_ids)|{focus}
    connected=[relation for relation in rels
               if relation.get("source") in scope or relation.get("target") in scope]
    connected.sort(key=lambda edge:(0 if edge.get("source") in scope and edge.get("target") in scope else 1,
                                    str(edge.get("source")),str(edge.get("target")),str(edge.get("rel"))))
    edge_page=connected[dependency_offset:dependency_offset+dependency_limit]
    def dependency_handle(edge):
        return {**edge,"navigation":{"kind":"typed-dependency-follow","conjugate_up":False,
            "authority":"canonical typed edge","revision":revision,
            "endpoints":[{"node":edge.get("source"),"query":{"project":project,
                "node":edge.get("source"),"direction":"dependency","from":edge.get("target")}},
                {"node":edge.get("target"),"query":{"project":project,
                "node":edge.get("target"),"direction":"dependency","from":edge.get("source")}}]}}
    internal=[dependency_handle(edge) for edge in edge_page
              if edge.get("source") in scope and edge.get("target") in scope]
    boundary=[dependency_handle(edge) for edge in edge_page
              if not (edge.get("source") in scope and edge.get("target") in scope)]
    children=[]
    for ident in page_ids:
        row=_tree_row(nodes,ident);handle=child_handles[ident]
        row["share"]=handle.get("share",0.0)
        row["descent"]={"kind":"containment-descent","authority":"conceptric.children_view",
            "revision":revision,"query":{"project":project,"node":ident,
                                           "direction":"down","from":focus}}
        children.append(row)
    ascent={"kind":"containment-ascent","authority":"conceptric.identity_chain",
            "revision":revision,"from":focus,"resolved_parent":identity[-1]["id"] if identity else None,
            # The query names the child, not a cached parent. The server resolves
            # its enclosing context again after any intervening edit or move.
            "query":{"project":project,"node":focus,"direction":"up"},
            "rederive_on_follow":True,"available":bool(identity)}
    if goal:
        if len(goal)>2000:raise ValueError("reconstruction goal is too large")
        from laplace.engine import keeper_ring
        trace={}
        envelope=keeper_ring.reconstruct(nodes,focus,goal,repo_root=root,reach=net.get("reach"),
            fanout=6,max_depth=4,pull_fraction=0.0,trace=trace)
        semantic_return={"status":"LIVE_BOUNDED","authority":"keeper_ring.reconstruct + MechanicalKeeper.pull_up",
            "revision":revision,"goal":goal,"visited":trace.get("visited",0),"return":envelope,
            "omission_residual":{"max_depth":4,"fanout":6,
                "negative_count":len(envelope.get("negatives") or []),
                "note":"Mechanical bounded reconstruction; no spectral chart was inferred."}}
    else:
        semantic_return={"status":"NOT_RUN","authority":"keeper_ring.reconstruct",
            "reason":"Navigation alone has no reconstruction goal, so no semantic pull-up was executed."}
    uncontained_ids=(sorted(ident for ident,value in nodes.items()
        if ident!=net.get("root") and (not value.get("parent") or value.get("parent") not in nodes))
        if focus==net.get("root") else [])
    uncontained_page=uncontained_ids[uncontained_offset:uncontained_offset+limit]
    return {"schema_version":"laplace.concept-tree/1","project":project,
            "revision":revision,"root_id":net.get("root"),"request":request,
            "current":_tree_row(nodes,focus),"ancestors":ancestors,
            "identity_chain":ancestors,
            "ancestors_omitted":ancestors_omitted,
            "children":children,"navigation":{"ascent":ascent},
            "children_total":len(child_ids),"children_offset":offset,
            "children_next_offset":offset+limit if offset+limit<len(child_ids) else None,
            "children_omitted":max(0,len(child_ids)-len(page_ids)),
            "uncontained":[_tree_row(nodes,ident) for ident in uncontained_page],
            "uncontained_total":len(uncontained_ids),"uncontained_offset":uncontained_offset,
            "uncontained_next_offset":uncontained_offset+limit
                if uncontained_offset+limit<len(uncontained_ids) else None,
            "dependencies":{"internal":internal,"boundary":boundary,
                "total":len(connected),"offset":dependency_offset,
                "next_offset":dependency_offset+dependency_limit
                    if dependency_offset+dependency_limit<len(connected) else None,
                "omitted":max(0,len(connected)-len(edge_page))},
            "relation_diagnostics":list(net.get("relation_diagnostics") or []),
            "hierarchy_gaps":hierarchy_gaps,
            "omission_residual":{"children_not_shown":max(0,len(child_ids)-len(page_ids)),
                "dependencies_not_shown":max(0,len(connected)-len(edge_page)),
                "ancestors_not_shown":ancestors_omitted},
            "semantic_return":semantic_return,
            "navigation_semantics":{"supported":[
                "grade descent through conceptric.children_view",
                "live enclosing-context ascent through conceptric.identity_chain",
                "bounded goal reconstruction through keeper_ring.reconstruct when goal is supplied",
                "typed dependency traversal kept distinct from containment"],
                "limitations":[
                "identity-chain ascent is a live containment re-projection, not browser history",
                "dependency traversal is not conjugate UP",
                "no materialized project-corpus Atlas chart or transition-map record is available"]},
            "atlas_conjugate":{"status":"UNAVAILABLE",
                "authority":"DESIGN_2026-08-24_the-conjugate-serve.md (SEED)",
                "reason":"No materialized per-block Atlas chart or transition map is registered for this project corpus; no spectral coordinates were invented."}}


def focus_projection(project:str,node:str,root:Path|None=None,max_nodes:int=32,
                     max_depth:int=4,dependency_limit:int=120) -> dict:
    """Bounded recursive containment consumed by a node-focused authoring context."""
    root=(root or _root()).resolve();net=_network(project,root)
    if not net or node not in (net.get("nodes") or {}):
        raise ValueError("focused concept node is unavailable")
    from laplace.engine import conceptric
    nodes=net["nodes"];max_nodes=max(1,min(128,int(max_nodes)))
    max_depth=max(0,min(8,int(max_depth)));dependency_limit=max(1,min(240,int(dependency_limit)))
    pending=[(node,0,None)];seen=set();projected=[];depth_frontier=[]
    while pending and len(projected)<max_nodes:
        ident,depth,share=pending.pop(0)
        if ident in seen or ident not in nodes:continue
        seen.add(ident);row=_tree_row(nodes,ident);row.update(depth=depth,share=share)
        projected.append(row)
        handles=[handle for handle in conceptric.children_view(net,ident)
                 if handle.get("id") in nodes and nodes[handle["id"]].get("parent")==ident]
        if depth>=max_depth:
            depth_frontier.extend(handle["id"] for handle in handles)
        else:
            pending.extend((handle["id"],depth+1,handle.get("share",0.0)) for handle in handles)
    chain=conceptric.identity_chain(net,node)
    identity=[{**_breadcrumb(nodes,link["id"]),"share":link["share"]}
              for link in chain[-100:] if link["id"] in nodes]
    rels,rows=_relations(project,root,net);scope={row["id"] for row in projected}
    connected=[edge for edge in rels if edge.get("source") in scope or edge.get("target") in scope]
    connected.sort(key=lambda edge:(str(edge.get("source")),str(edge.get("target")),str(edge.get("rel"))))
    dependency_page=connected[:dependency_limit]
    boundary_ids=[]
    for edge in dependency_page:
        for endpoint in (edge.get("source"),edge.get("target")):
            if endpoint in nodes and endpoint not in scope and endpoint not in boundary_ids:
                boundary_ids.append(endpoint)
    boundary_page=boundary_ids[:40]
    residual={"complete":not pending and not depth_frontier and len(connected)<=dependency_limit
                         and len(chain)<=100 and len(boundary_ids)<=40,
        "node_limit":max_nodes,"depth_limit":max_depth,
        "queued_descendants_not_projected":len(pending),
        "known_children_beyond_depth":len(depth_frontier),
        "deeper_descendant_count_unknown":bool(depth_frontier),
        "dependencies_not_projected":max(0,len(connected)-len(dependency_page)),
        "boundary_nodes_not_projected":max(0,len(boundary_ids)-len(boundary_page)),
        "uplinks_not_projected":max(0,len(chain)-len(identity))}
    payload={"current":projected[0],"identity_chain":identity,"descendants":projected[1:],
             "dependencies":dependency_page,
             "boundary_nodes":[_tree_row(nodes,ident) for ident in boundary_page],
             "omission_residual":residual}
    return {"schema_version":"laplace.concept-focus/1","project":project,"authority":{
                "hierarchy":"conceptric.children_view","uplinks":"conceptric.identity_chain",
                "dependencies":"canonical typed edge"},
            **payload,"revision":hashlib.sha256(json.dumps(payload,sort_keys=True,
                ensure_ascii=False,default=str,separators=(",",":")).encode()).hexdigest()}


_HISTORY_FIELDS=("kind","essence","status","parent","containment_grade","members","source_refs","projection","authored")

def _history_snapshot(net:dict|None,ident:str) -> dict|None:
    if not net:return None
    node=(net.get("nodes") or {}).get(ident)
    if not node:return None
    value={"id":ident,"label":_label(node,ident),"kind":node.get("kind"),
        "essence":node.get("essence") or "","status":node.get("status"),
        "parent":node.get("parent"),"containment_grade":node.get("grade"),
        "members":list(node.get("members") or []),"source_refs":_source_refs(node),
        "projection":dict(node.get("projection") or {}),"authored":bool(node.get("authored"))}
    return value

def _history_diff(before:dict|None,after:dict|None) -> list[dict]:
    if before is None and after is None:return []
    if before is None:return [{"field":"existence","before":"ABSENT","after":"PRESENT"}]
    if after is None:return [{"field":"existence","before":"PRESENT","after":"ABSENT"}]
    return [{"field":key,"before":before.get(key),"after":after.get(key)}
            for key in _HISTORY_FIELDS if before.get(key)!=after.get(key)]

def _history_ancestors(net:dict|None,ident:str) -> list[str]:
    if not net:return []
    nodes=net.get("nodes") or {};out=[];seen={ident};cursor=ident
    while cursor in nodes:
        parent=nodes[cursor].get("parent")
        if not parent or parent not in nodes or parent in seen:break
        out.append(parent);seen.add(parent);cursor=parent
    return out

def _history_network(project:str,root:Path,records:list[dict]) -> dict|None:
    from laplace.research import corpus_ingest as ci
    tex=ci.resolve_corpus(root,project)
    if tex is None:return None
    return ci.build_corpus_network(tex,semantic=False,overlay=records,name=project,repo_root=root)

def _history_relevant_indices(base:dict|None,rows:list[dict],focus:str) -> list[int]:
    """Track containment from exact rewire operations without rebuilding every prefix."""
    nodes=(base or {}).get("nodes") or {};parents={ident:node.get("parent") for ident,node in nodes.items()}
    live=set(nodes)
    def within(ident):
        cursor=str(ident or "");seen=set()
        while cursor and cursor not in seen:
            if cursor==focus:return True
            seen.add(cursor);cursor=str(parents.get(cursor) or "")
        return False
    selected=[]
    for index,row in enumerate(rows):
        node,target=str(row.get("node") or ""),str(row.get("target") or "")
        before=within(node) or within(target) or str(row.get("supersedes") or "")==focus
        kind=row.get("kind")
        if kind=="add-node" and node:
            live.add(node);parents[node]=row.get("parent")
        elif kind=="move-node" and node in live:
            parents[node]=target or None
        elif kind=="delete-node" and node in live:
            fallback=parents.get(node)
            for child,parent in list(parents.items()):
                if parent==node:parents[child]=fallback
            live.discard(node);parents.pop(node,None)
        after=within(node) or within(target)
        if before or after or node==focus or target==focus:selected.append(index)
    return selected

def _history_relations(project:str,root:Path,net:dict|None) -> list[dict]:
    if not net:return []
    return _relations(project,root,net)[0]

def _history_current_impact(project:str,root:Path,ids:list[str]) -> list[dict]:
    net=_network(project,root) or {};nodes=net.get("nodes") or {}
    placed,sections,_reader=_placement(project,root);by_section={str(row.get("id")):row for row in sections}
    try:literature_inputs=_literature_inputs(project,root,{"sections":sections})
    except (OSError,ValueError,TypeError,json.JSONDecodeError):literature_inputs=None
    out=[]
    # RD-HISTORY: this helper owns its bounded selection -- the deduplicated first 80 impacted ids -- and
    # assesses support for each existing one exactly once, over the ONE literature-input read above.
    # (It used logical_plan's local page selection `hydrate_ids`, a name it never bound.)
    for ident in list(dict.fromkeys(item for item in ids if item))[:80]:
        node=nodes.get(ident);locations=[]
        for placement in placed.get(ident,[]):
            section=by_section.get(str(placement.get("id"))) or {}
            source=section.get("source") or {}
            locations.append({**placement,"source_files":list(source.get("source_files") or [])})
        try:
            source_support = _source_support(project,ident,root,net,literature_inputs) if node else None
        except (OSError,ValueError,TypeError,json.JSONDecodeError):source_support=None
        out.append({"id":ident,"label":_label(node,ident) if node else ident,
            "kind":node.get("kind") if node else None,"available":bool(node),
            "source_refs":_source_refs(node) if node else [],"source_support":source_support,
            "reader_locations":locations,
            "posture":"CURRENT_JOIN_NOT_HISTORICAL"})
    return out

def history(project:str,node:str,offset:int=0,limit:int=12,record_id:str="",root:Path|None=None) -> dict|None:
    """Project exact rewire events into bounded before/after logical impact.

    The ledger did not pin historical corpus source bytes. Before/after networks
    are therefore honest re-projections of exact operations over the current
    source, never claimed as historical snapshots or automatic reproof.
    """
    from laplace.research import corpus_ingest as ci
    from laplace.manuscript import manuscript_source, review_surface
    root=(root or _root()).resolve();rows=[row for row in ci.rewire_list(root,project)
        if isinstance(row,dict) and row.get("kind") in ci._REWIRE_KINDS]
    current=_network(project,root)
    if current is None and not any(row.get("node")==node for row in rows):return None
    base=_history_network(project,root,[])
    relevant=_history_relevant_indices(base,rows,node)
    if record_id:
        relevant=[index for index in relevant if rows[index].get("id")==record_id]
    relevant=list(reversed(relevant));offset=max(0,int(offset));limit=max(1,min(20,int(limit)))
    selected=relevant[offset:offset+limit];cache={}
    def network(count):
        if count not in cache:cache[count]=_history_network(project,root,rows[:count])
        return cache[count]
    events=[];impact_ids=[node]
    for index in selected:
        event=rows[index];before,after=network(index),network(index+1)
        subject=str(event.get("node") or "");before_subject=_history_snapshot(before,subject);after_subject=_history_snapshot(after,subject)
        before_focus=_history_snapshot(before,node);after_focus=_history_snapshot(after,node)
        ancestor_ids=list(dict.fromkeys(_history_ancestors(before,subject)+_history_ancestors(after,subject)))
        ancestor_effects=[]
        for ident in ancestor_ids:
            old,new=_history_snapshot(before,ident),_history_snapshot(after,ident);diff=_history_diff(old,new)
            if not diff and not ((old or new) or {}).get("authored"):continue
            authored=bool((old or new or {}).get("authored"))
            ancestor_effects.append({"id":ident,"label":(new or old or {}).get("label") or ident,
                "changes":diff,"posture":"SEMANTIC_REVIEW_REQUIRED" if authored else "MECHANICALLY_RECOMPUTED",
                "reason":"Authored parent meaning is preserved, but its child changed; review whether that interpretation still fits."
                         if authored else "Membership, grade, or derived summary is mechanically recomputed from current children."})
            impact_ids.append(ident)
        before_rel=_history_relations(project,root,before);after_rel=_history_relations(project,root,after)
        relation_keys=lambda values:{json.dumps({key:r.get(key) for key in ("source","target","rel","axis","rationale")},sort_keys=True):r for r in values}
        old_rel,new_rel=relation_keys([r for r in before_rel if subject in {r.get("source"),r.get("target")}]),relation_keys([r for r in after_rel if subject in {r.get("source"),r.get("target")}])
        relation_changes=[{"state":"REMOVED","relation":old_rel[key]} for key in sorted(set(old_rel)-set(new_rel))]+[{"state":"ADDED","relation":new_rel[key]} for key in sorted(set(new_rel)-set(old_rel))]
        dependents=[]
        for relation in after_rel:
            if relation.get("target")!=subject:continue
            ident=str(relation.get("source") or "");snap=_history_snapshot(after,ident)
            dependents.append({"id":ident,"label":(snap or {}).get("label") or ident,
                "relation":relation.get("rel"),"posture":"SEMANTIC_REVIEW_REQUIRED",
                "reason":"A typed dependency points to the changed object; no proof or prose was automatically updated."})
            impact_ids.append(ident)
        operation={key:event.get(key) for key in ("id","ts","kind","by","node","target","parent","node_kind","essence","value","rel","axis","rationale","ord","narrative","ref","supersedes") if key in event}
        events.append({"record_index":index,"operation":operation,
            "summary":review_surface._friction_summary(event),
            "subject":{"id":subject,"before":before_subject,"after":after_subject,
                       "changes":_history_diff(before_subject,after_subject)},
            "focused_effect":{"id":node,"before":before_focus,"after":after_focus,
                              "changes":_history_diff(before_focus,after_focus)},
            "containment":{"before_ancestors":_history_ancestors(before,subject),
                           "after_ancestors":_history_ancestors(after,subject),
                           "ancestor_effects":ancestor_effects},
            "relation_changes":relation_changes,"affected_dependents":dependents,
            "posture":"MECHANICALLY_RECOMPUTED" if before is not None and after is not None else "HISTORICAL_BASIS_UNAVAILABLE",
            "guarantees":{"proof_rechecked":False,"manuscript_rewritten":False,
                          "scientific_validity_reassessed":False}})
        impact_ids.append(subject)
    source=manuscript_source.resolve(project,repo_root=root)
    basis_status="REPROJECTED_ON_CURRENT_SOURCE" if base is not None else "HISTORICAL_BASIS_UNAVAILABLE"
    current_focus=focus_projection(project,node,root) if current and node in (current.get("nodes") or {}) else None
    return {"schema_version":"laplace.concept-history/1","project":project,"node":node,
        "current":current_focus,"basis":{"status":basis_status,
            "source_revision":source.get("revision"),"source_root":source.get("root"),
            "ledger_revision":"sha256:"+hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest(),
            "reason":"Rewire operations are exact. Historical corpus source bytes were not pinned, so before/after structure is reprojected over the current source."},
        "history":events,"impact":{"objects":_history_current_impact(project,root,impact_ids),
            "posture":"No dependent was re-proven and no manuscript prose was propagated."},
        "pagination":{"offset":offset,"limit":limit,"total":len(relevant),
            "next_offset":offset+len(selected) if offset+len(selected)<len(relevant) else None},
        "limitations":["Historical source bytes are unavailable unless another canonical owner pinned them.",
                       "Reader locations and source references are current joins, not historical placement snapshots."]}


OBLIGATION_STATES=("open","addressed","withdrawn")
OBLIGATION_WORK_KINDS=("concept","research","literature","computation","formal","author-decision")


def _source_refs(node:dict) -> list:
    """Return source locators without inventing a second provenance vocabulary."""
    raw=node.get("source") or node.get("sources") or node.get("ref")
    if raw is None:return []
    return list(raw) if isinstance(raw,list) else [raw]

def _literature_inputs(project:str,root:Path,structure:dict|None=None,*,support_context=None):
    from laplace.research import references_surface as references, literature_support
    if structure is not None and support_context is None:support_context=literature_support._scope_inputs(project,root,{})
    manuscript=support_context['manuscript'] if support_context is not None else references._manuscript(project,root)
    associations=(support_context['associations'] if support_context is not None else references._load_associations(manuscript) if manuscript else [])
    citations=None
    if structure is not None:
        source=support_context['source'];spans=support_context['citations']
        citations=literature_support.citation_context(project,root,spans,structure=structure,
            selected_source=source,heading_spans_by_file=support_context['heading_cache'])
    return associations,citations,{"associations_omitted":0,
        "citations_omitted":0 if citations is not None else None,
        "citation_projection":"CANONICAL_SECTIONS" if citations is not None else "ON_DEMAND"},support_context

def _source_support(project:str,ident:str,root:Path,net:dict,inputs=None,*,source_record=None,read_context=None) -> dict:
    from laplace.research import literature_support
    associations,citations,omission,support_context=inputs or _literature_inputs(project,root)
    return {**literature_support.for_node(project,ident,root,net=net,
        associations=associations,citations=citations,support_context=support_context,source_record=source_record,read_context=read_context,
        **({'research_store':support_context['research_store'],'research_project_root':support_context['research_project_root']}
           if support_context is not None else {})),"omission":omission}


def _placement(project:str,root:Path,*,support_context=None) -> tuple[dict,list,dict]:
    """Join optional L2 placement; L1 remains readable when no plan is declared."""
    try:
        from laplace.manuscript import project_structure
        joined=project_structure.state(project,root,include_support=False,
            **({'support_context':support_context} if support_context is not None else {}))
        if support_context is not None:support_context['structure']=joined
    except ValueError as exc:
        return {},[],{"status":"UNDECLARED","reason":str(exc),"revision":None}
    sections=joined.get("sections") or []
    placed={}
    for section in sections:
        for ident in list(section.get("node_ids") or [])+list(section.get("beat_ids") or []):
            placed.setdefault(str(ident),[]).append({key:section.get(key) for key in
                ("id","title","kind","number","order","parent_id")})
    status="DECLARED" if sections else "UNDECLARED"
    reason=None if sections else "No L2 reader order is declared; logical planning remains available."
    return placed,sections,{"status":status,"reason":reason,"revision":joined.get("revision"),
        "source_outline":joined.get("source_outline") or [],
        "omitted_sections":0}


def _obligation_issue(ident:str,node:dict,nodes:dict,relations:list) -> dict|None:
    value=(node.get("projection") or {}).get("obligation")
    if not isinstance(value,dict):
        return {"kind":"malformed-obligation","id":ident,"reason":"question has no obligation metadata"}
    missing=[key for key in ("target","work_kind","discharge_condition","state") if not value.get(key)]
    if missing:return {"kind":"malformed-obligation","id":ident,
        "reason":"obligation is missing "+", ".join(missing)}
    target=value.get("target") or {};kind=target.get("kind")
    if kind=="node" and target.get("node_id") not in nodes:
        return {"kind":"unbound-obligation","id":ident,"reason":"target node is unavailable"}
    if kind=="relation" and not any(r.get("source")==target.get("source") and
            r.get("target")==target.get("target") and r.get("rel")==target.get("rel")
            for r in relations):
        return {"kind":"unbound-obligation","id":ident,"reason":"target relation is unavailable"}
    if kind not in {"node","relation"}:
        return {"kind":"malformed-obligation","id":ident,"reason":"target kind must be node or relation"}
    return None


def _obligation_basis(project:str, node:dict, obligation:dict, root:Path, snapshot, cache:dict) -> dict:
    """Consumed identities from existing owners, never an independent verification."""
    net,relations,_rows=snapshot;nodes=net.get("nodes") or {}
    target=obligation.get("target") if isinstance(obligation.get("target"),dict) else {}
    ids=([target.get("node_id")] if target.get("kind")=="node" else
         [target.get("source"),target.get("target")])
    targets=[]
    for ident in dict.fromkeys(ids):
        if not ident:continue
        if ident not in cache:
            cache[ident]=identity(project,ident,root,network_snapshot=snapshot)
        value=cache[ident]
        targets.append({"id":ident,"content_revision":value.get("content_revision") if value else None})
    relation=next((r for r in relations if all(r.get(k)==target.get(k)
        for k in ("source","target","rel"))),None) if target.get("kind")=="relation" else None
    question={"meaning":node.get("essence"),**{key:obligation.get(key) for key in
        ("target","work_kind","discharge_condition")}}
    question_revision=hashlib.sha256(json.dumps(question,sort_keys=True,default=str).encode()).hexdigest()
    evidence=[]
    for ref in obligation.get("evidence") or []:
        ident=ref if isinstance(ref,str) else ref.get("id") if isinstance(ref,dict) else None
        ident=ident if isinstance(ident,str) else None
        value=None
        if ident in nodes:
            if ident not in cache:cache[ident]=identity(project,ident,root,network_snapshot=snapshot)
            value=cache[ident]
            evidence.append({"reference":ref,"owner":"concept","id":ident,
                "revision":value.get("content_revision"),"currentness":"CURRENT"})
        else:
            if ("result",ident) not in cache:
                from laplace.research import research_context, research_records
                item,manuscript=research_context.project(project,root)
                project_root=research_context.project_root(item,root) if item else None
                found=research_records.result_bindings(manuscript,[ident],project_root) if manuscript and ident else {}
                cache[("result",ident)]=next(iter(found.get("bindings") or []),None)
            value=cache[("result",ident)]
            evidence.append({"reference":ref,"owner":"research-result" if value else None,
                "id":ident,"revision":value.get("revision") if value else None,
                "currentness":value.get("currentness") if value else "UNKNOWN",
                "dependencies":value.get("dependencies") if value else None})
        if isinstance(ref,dict) and evidence[-1].get("revision"):
            declared=ref.get("content_revision") or ref.get("revision")
            if declared and declared!=evidence[-1]["revision"]:
                evidence[-1].update(currentness="STALE",reason="Declared evidence revision differs from its current owner.")
    return {"question_revision":question_revision,"targets":targets,
            "target_resolved":(target.get("node_id") in nodes if target.get("kind")=="node"
                               else relation is not None if target.get("kind")=="relation" else False),
            "relation":relation,"evidence":evidence}


def _obligation_currentness(consumed,live:dict,state:str) -> dict:
    if state=="open":return {"status":"OPEN","reason":"The question remains open."}
    if not isinstance(consumed,dict):
        return {"status":"UNPINNED_LEGACY","reason":"This disposition did not pin its consumed target and evidence revisions."}
    changed=[key for key in ("question_revision","targets","relation","evidence")
             if consumed.get(key)!=live.get(key)]
    if changed:return {"status":"STALE","changed":changed,
        "reason":"Consumed question, target or evidence changed; review the recorded disposition."}
    if any(row.get("currentness")=="STALE" for row in live["evidence"]):
        return {"status":"STALE","changed":["evidence_currentness"],
            "reason":"Consumed evidence is stale in its canonical owner; review the disposition."}
    unavailable=not live.get("target_resolved",True) or any(not row.get("content_revision") for row in live["targets"]) or any(
        row.get("currentness")!="CURRENT" or not row.get("revision") for row in live["evidence"])
    return {"status":"UNKNOWN" if unavailable else "CURRENT",
        "reason":"Some consumed identities cannot be resolved." if unavailable else
                 "Consumed identities still match. Addressed remains a recorded disposition, not verification."}


def _derivation_identity_join(project:str,root:Path,nodes:dict) -> tuple[dict,dict]:
    """Join the derivative aspiration face only where it carries explicit L1 ids."""
    try:
        from laplace.pipeline import derivation_organ
        from laplace.research import research_context, research_records
        _record,manuscript=research_context.project(project,root)
        sheet=derivation_organ.read_sheet(manuscript) if manuscript else {"present":False,"chain":[]}
    except (OSError,ValueError):
        sheet={"present":False,"chain":[]}
    by_node={};bound=[];unbound=[]
    for link in sheet.get("chain") or []:
        explicit=[]
        if isinstance(link.get("node_id"),str):explicit.append(link["node_id"])
        if isinstance(link.get("from_ids"),list):explicit.extend(
            ident for ident in link["from_ids"] if isinstance(ident,str))
        if isinstance(link.get("to_id"),str):explicit.append(link["to_id"])
        explicit=list(dict.fromkeys(explicit));live=[ident for ident in explicit if ident in nodes]
        row={**link,"logical_object_ids":live}
        if not explicit:
            unbound.append({**row,"binding_status":"UNBOUND_LEGACY",
                "binding_reason":"the derivative link carries no explicit canonical logical identity"})
        elif len(live)!=len(explicit):
            unbound.append({**row,"binding_status":"UNBOUND_MISSING_OBJECT",
                "binding_reason":"one or more explicit logical identities are unavailable"})
        else:
            bound.append({**row,"binding_status":"BOUND"})
            for ident in live:by_node.setdefault(ident,[]).append(row)
    face={"present":bool(sheet.get("present")),"aspiration":sheet.get("aspiration") or {"present":False},
        "reach":sheet.get("reach") or {},"bound_links":bound,"unbound_links":unbound,
        "authority":"pipeline.derivation_organ.read_sheet; joined only by node_id/from_ids/to_id"}
    return by_node,face


def logical_plan(project:str,focus:str="",offset:int=0,limit:int=200,
                 root:Path|None=None,*,attention:bool=False) -> dict|None:
    """Human/machine logical plan over the canonical corpus projection.

    This is a joined facade, not a persistent plan.  Meanings stay on nodes,
    dependencies stay in the typed relation projection, evidence stays behind
    its existing bindings, and reader placement is joined from L2 when present.
    """
    root=(root or _root()).resolve();net=_network(project,root)
    if not net:return None
    from laplace.research.corpus_ingest import DERIVATION_KINDS, LOGICAL_KINDS, dep_grade
    nodes=net.get("nodes") or {};relations,rows=_relations(project,root,net)
    grades=dep_grade(net)
    # Select logical subjects before result/source/Work evidence hydration.
    logical_ids = [ident for ident, node in nodes.items()
                   if node.get('kind') in set(LOGICAL_KINDS) | set(DERIVATION_KINDS)]
    logical_ids.sort(key=lambda ident: (nodes[ident].get('kind') == 'question',
                                      _label(nodes[ident], ident).casefold(), ident))
    if focus in logical_ids:
        logical_ids = [focus] + [ident for ident in logical_ids if ident != focus]
    attention_ids = None
    if attention and focus in logical_ids:
        attention_ids = {focus} | {row.get('target') for row in relations if row.get('source') == focus}
        attention_ids.update(ident for ident in logical_ids if any(
            ((nodes[ident].get('projection') or {}).get('obligation') or {}).get('target', {}).get(key) in attention_ids
            for key in ('node_id', 'source', 'target')))
    ordered_ids = [ident for ident in logical_ids if attention_ids is None or ident in attention_ids]
    offset, limit = max(0, int(offset)), max(1, min(500, int(limit)))
    hydrate_ids = set(ordered_ids[offset:offset + limit])
    from laplace.research import literature_support
    read_context={}
    support_context=literature_support._scope_inputs(project,root,read_context,network_snapshot=net)
    placed,sections,reader_order=_placement(project,root,support_context=support_context)
    logical=[];issues=[];obligations=[];basis_cache={}
    from laplace.work import project_work
    raw_work=project_work._tasks(project,root)
    work_by_obligation={}
    related_work = {key: value for key, value in raw_work.items() if value.get('obligation_id') in hydrate_ids}
    for task in project_work._resolved_tasks(related_work,root,read_context=read_context):
        if task.get("obligation_id"):
            work_by_obligation.setdefault(task["obligation_id"],[]).append({
                **{key:task.get(key) for key in ("id","title","status","evidence","currentness","blocked_by")},
                "recorded_status":raw_work[task["id"]].get("status")})
    history_by_node={}
    for event in rows:history_by_node.setdefault(event.get("node"),[]).append(event)
    try:literature_inputs=_literature_inputs(project,root,{"sections":sections},support_context=support_context)
    except (OSError,ValueError,TypeError,json.JSONDecodeError):literature_inputs=None
    support_gaps=[]
    derivation_by_node,derivation_face=_derivation_identity_join(project,root,nodes)
    relation_by_source={}
    for relation in relations:relation_by_source.setdefault(relation.get("source"),[]).append(relation)
    for ident,node in nodes.items():
        if node.get("kind") not in set(LOGICAL_KINDS)|set(DERIVATION_KINDS):continue
        projection=node.get("projection") or {};obligation=projection.get("obligation")
        outgoing=relation_by_source.get(ident,[])
        try:source_support=_source_support(project,ident,root,net,literature_inputs)
        except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
            source_support={"node":ident,"sources":[],"own_evidence":[],"authored_proof":False,
                "gaps":[{"kind":"support-projection-unavailable","reason":str(exc)}],
                "qualification":"OPEN","independent_verification":"NOT_ASSERTED",
                "omission":{"associations_omitted":0,"citations_omitted":0}}
        support_gaps.extend({"node_id":ident,**gap} for gap in source_support.get("gaps") or [])
        row={"id":ident,"kind":node.get("kind"),"meaning":node.get("essence") or "",
            "grade":grades.get(ident,0),
            "containment_grade":node.get("grade",0),"parent":node.get("parent"),
            "members":list(node.get("members") or []),
            "label":_label(node,ident),"title":_short_title(node),"status":node.get("status"),
            "source_refs":_source_refs(node),"placements":placed.get(ident,[]),
            "placed":ident in placed,"evidence_bindings":list(projection.get("result_bindings") or []),
            "derivation_links":derivation_by_node.get(ident,[]),
            "premises":[r for r in outgoing if r.get("rel")=="prerequisite"],
            "support":[r for r in outgoing if r.get("rel") in {"support","validated_by"}],
            "counterevidence":[r for r in outgoing if r.get("rel")=="counterevidence"],
            "source_support":source_support,
            "relations":outgoing}
        logical.append(row)
        if node.get("kind")=="question" and ident in hydrate_ids:
            issue=_obligation_issue(ident,node,nodes,relations)
            if issue:issues.append(issue)
            value=obligation if isinstance(obligation,dict) else {}
            live=_obligation_basis(project,node,value,root,(net,relations,rows),basis_cache)
            target=value.get("target") if isinstance(value.get("target"),dict) else {};target_ids=[target.get(key) for key in ("node_id","source","target")]
            locations={location["id"]:location for target_id in target_ids for location in placed.get(target_id,[])}
            events=history_by_node.get(ident,[])
            origins=[{key:event.get(key) for key in ("id","ts","by","kind")} for event in events if event.get("kind")=="add-node"]
            obligations.append({"id":ident,"meaning":row["meaning"],**value,
                "marker":"DECIDE" if value.get("work_kind")=="author-decision" else "CONFIRM",
                "decision_permission":{"status":"NOT_ESTABLISHED",
                    "reason":"Caller-supplied by records an audit origin; this change door does not establish human author consent."}
                    if value.get("work_kind")=="author-decision" else None,
                "currentness":_obligation_currentness(value.get("consumed_basis"),live,value.get("state")),
                "live_basis":live,"placements":list(locations.values()),
                "placement_precision":"SECTION_ONLY" if locations else "UNPLACED",
                "work":work_by_obligation.get(ident,[]),
                "origin":{"status":"RECORDED" if origins else "UNKNOWN","records":origins,
                    "reason":"Exact creation records; originating private conversation is not asserted."},
                "history":{"operation":"concept_history","payload":{"project":project,"node":ident}},
                "verification":"NOT_ESTABLISHED_BY_DISPOSITION","issue":issue})
    logical.sort(key=lambda row:(row["kind"]=="question",row["label"].casefold(),row["id"]))
    container_rows=[]
    for ident,node in nodes.items():
        if ident!=net.get("root") and (node.get("kind") in set(LOGICAL_KINDS)|set(DERIVATION_KINDS) or not node.get("members")):continue
        container_rows.append({**_tree_row(nodes,ident),"members":list(node.get("members") or [])})
    container_rows.sort(key=lambda row:(0 if row["id"]==net.get("root") else 1,-int(row.get("grade") or 0),row["label"].casefold(),row["id"]))
    container_limit=100;containers=container_rows[:container_limit]
    selected=next((row for row in logical if row["id"]==focus),None) if focus else None
    ordered=([selected]+[row for row in logical if row is not selected]) if selected else logical
    if attention and selected:
        # Resolve immediate objects before pagination; a premise may be anywhere
        # in a book-length corpus, independently of alphabetical page boundaries.
        ids={selected["id"]}
        ids.update(r.get("target") for r in selected["relations"])
        ids.update(o["id"] for o in obligations if
            (o.get("target") or {}).get("node_id") in ids or
            (o.get("target") or {}).get("source")==selected["id"] or
            (o.get("target") or {}).get("target")==selected["id"])
        ordered=[row for row in ordered if row["id"] in ids]
    offset=max(0,int(offset));limit=max(1,min(500,int(limit)));page=ordered[offset:offset+limit]
    from laplace.manuscript import manuscript_source
    source=manuscript_source.resolve(project,repo_root=root)
    plan_revision=_revision(nodes,relations,rows)
    return {"schema_version":"laplace.logical-plan/1","project":project,
        "revision":plan_revision,
        # The same `concept-network` home the `concept` read publishes, and the
        # `selected-edition` home `source_currentness` mirrors: one token each, so a caller
        # can see that `logical_plan.revision` and `concept.revision` ARE the same value
        # (measured: one mint at :123/:136, one at :752, both over the same snapshot) rather
        # than discovering it by refusal.  `revision` is retained beside the token as a
        # `identity_doors.RETAINED` row ("logical_plan.revision"), with its consumer and that
        # register's dated expiry; it is the FIRST row the synthesis can delete, because this
        # door already passes on the token alone.
        "identities":identity_doors.identities(
            ("concept-network",project,plan_revision),
            ("selected-edition",project,source.get("revision"))),
        "authority":{
            "objects":"corpus_ingest.corpus_network","edits":"corpus_friction rewire records",
            "relations":"corpus_ingest.relation_projection","reader_order":"projection-plan ledger",
            "evidence":"canonical result/source bindings"},
        # `source_currentness.revision` was this read's fourth name for the `selected-edition`
        # value (3606664b..., five names across three reads) and `reader_order.revision` was
        # its third name for the `plan` value (sha256:d55ee..., three names).  Both are
        # deleted: the token above is where this read publishes those two homes, and nothing
        # in the tree reads either key -- `_currentness` (front_research_compute.py:102) reads
        # `status` only, and no consumer indexes `reader_order["revision"]`.
        "source_currentness":{key:source.get(key) for key in
            ("status","root","edition","read_only","diagnostics")},
        "reader_order":{key:item for key,item in (reader_order or {}).items()
                        if key!="revision"} if isinstance(reader_order,dict) else reader_order,
        "selected":selected,"objects":page,
        "containers":containers,"containers_omitted":max(0,len(container_rows)-len(containers)),
        "derivation_face":derivation_face,
        "placed_count":sum(bool(row["placed"]) for row in logical),
        "unplaced_count":sum(not row["placed"] for row in logical),
        "obligations":obligations,"issues":issues,"source_support_gaps":support_gaps[:200],
        "source_support_gaps_omitted":max(0,len(support_gaps)-200),
        "relation_diagnostics":list(net.get("relation_diagnostics") or []),
        "omission":{"support_scope": "Returned object page only; other object evidence was not hydrated",
            "support_objects_assessed": len(hydrate_ids),
            "objects_total":len(logical),"objects_offset":offset,
            "objects_returned":len(page),"objects_omitted":len(logical)-len(page),
            "relations_total":len(relations),"sections_total":len(sections),
            "note":"Follow object identities and source references; absent L2 placement is explicit."}}


def logical_plan_context(project:str,node:str="",root:Path|None=None,*,
                         file:str="",line_start:int=0,line_end:int=0,
                         accepted_offset:int=0,accepted_limit:int=40,accepted_as_of:str="") -> dict|None:
    """Bound the machine context to the selected object and its immediate logic."""
    value=logical_plan(project,focus=node,root=root,limit=24,attention=True)
    if not value:return None
    if node and value.get("selected") is None:return None
    passage=None
    if file:
        if line_start<1 or line_end<line_start:raise ValueError("passage context needs positive source line_start and line_end")
        from laplace.manuscript import proposal_basis
        passage=proposal_basis.passage_context(root or _root(),project,
            {"file":file,"line_start":line_start,"line_end":line_end},value,
            accepted_offset=accepted_offset,accepted_limit=accepted_limit,accepted_as_of=accepted_as_of)
    if passage is not None:
        return {"schema_version":"laplace.logical-plan-context/1","project":project,
            "revision":value["revision"],"identities":value.get("identities") or {},
            "passage_context":passage,"source_currentness":value["source_currentness"],
            "reader_order":value["reader_order"]}
    selected=value.get("selected") or next(iter(value.get("objects") or []),None)
    if selected is None:return {key:value[key] for key in
        ("schema_version","project","revision","identities","source_currentness","reader_order",
         "omission")}
    ids={selected["id"]}
    for relation in selected.get("relations") or []:
        ids.update((relation.get("source"),relation.get("target")))
    objects=value["objects"]
    ids.update(row["id"] for row in objects)
    return {"schema_version":"laplace.logical-plan-context/1","project":project,
        **({"passage_context":passage} if passage else {}),
        "revision":value["revision"],"identities":value.get("identities") or {},
        "selected":selected,"objects":objects,
        "containers":value.get("containers") or [],"containers_omitted":value.get("containers_omitted",0),
        "obligations":[row for row in value["obligations"] if row.get("id") in ids or
            (row.get("target") or {}).get("node_id") in ids or
            (row.get("target") or {}).get("source") in ids or
            (row.get("target") or {}).get("target") in ids],
        "source_currentness":value["source_currentness"],"reader_order":value["reader_order"],
        "omission":{"attention_limit":24,"objects_not_in_attention":max(0,value["omission"]["objects_total"]-len(objects)),
            "navigation":"Use returned identities and source_refs to descend."},
        "complete_inventory":{"operation":"logical_plan",
            "payload":{"view":"catalog","offset":0,"limit":80},
            "purpose":"Page every canonical logical identity without copying each object's scientific body."}}


def logical_plan_operation_contract() -> dict:
    """Source-derived author operation contract for the editable logical stage."""
    from laplace.research.corpus_ingest import LOGICAL_KINDS
    from laplace.pipeline.schema import EDGE_RELATIONS
    return {"schema_version":"laplace.logical-plan-change-contract/1",
        "required":["project","operation","base_revision"],
        "authority":{"read_projection":"corpus_ingest.corpus_network",
            "author_edits":"corpus_friction rewire records through corpus_ingest.rewire_add",
            "reader_order":"projection-plan ledger (joined, never inferred from section order)",
            "work_routing":"project_work.task, only through route_obligation"},
        "representation":{"meaning":"node essence is the one authored meaning",
            "obligation":"a question logical node with obligation metadata in its existing projection slot",
            "anchor":"questions is a non-inferential typed relation; a relation target also retains its exact source/target/rel triple",
            "distinctions":"goal remains project orientation; administrative friction remains friction; neither is silently recast as a scientific question",
            "persistence":"no logical-plan, obligations, claim, outline or feedback store is added"},
        "states":list(OBLIGATION_STATES),"work_kinds":list(OBLIGATION_WORK_KINDS),
        "object_kinds":list(LOGICAL_KINDS),"relations":sorted(EDGE_RELATIONS),
        "operations":{
            "add_object":{"required":["node","kind","meaning"],"optional":["parent","source_ref"]},
            "edit_meaning":{"required":["node","meaning"]},
            "connect":{"required":["source","target","relation","rationale"]},
            "add_obligation":{"required":["node","meaning","target","work_kind","discharge_condition"]},
            "update_obligation":{"required":["node","state"]},
            "route_obligation":{"required":["node"]}},
        "obligation_target":{"node":{"required":["kind","node_id"]},
            "relation":{"required":["kind","source","target","rel"]}},
        "safeguards":["base_revision must match","addressed or withdrawn carries evidence or disposition",
            "addressed is not verification","routing is explicit and retains obligation identity",
            "rerouting selects existing work without rewriting its authored specification or renewing its completion"]}


def _valid_target(target:Any,nodes:dict,relations:list) -> str|None:
    if not isinstance(target,dict):return "obligation target must be an object"
    if target.get("kind")=="node":
        return None if target.get("node_id") in nodes else "obligation target node is unavailable"
    if target.get("kind")=="relation":
        return None if any(r.get("source")==target.get("source") and
            r.get("target")==target.get("target") and r.get("rel")==target.get("rel")
            for r in relations) else "obligation target relation is unavailable"
    return "obligation target kind must be node or relation"


def logical_plan_change(payload:dict,root:Path|None=None) -> tuple[int,dict]:
    """Change L1 through its canonical writer; optionally route one question to work."""
    try:identity_doors.admit_expected(payload, "logical_plan_change")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    except identity_doors.IdentityRefused as refused:return 409,identity_doors.refuse({"error":str(refused)},refused)
    root=(root or _root()).resolve();project=str(payload.get("project") or "")
    current=logical_plan(project,root=root)
    if not current:return _no_plan_to_change(project,root)
    try:
        # `base_revision` here names the `concept-network` home -- the same home
        # `concept_change`'s `base_revision` and `structure_change bind_results`'s
        # `expected_concept_revision` name, measured: one value, three names (GRAMMAR.md §0.3).
        identity_doors.gate("logical_plan_change", supplied=payload,
                            homes=[("concept-network",project,current["revision"])],
                            required=["base_revision"],
                            said="logical plan revision conflict")
    except identity_doors.IdentityRefused as refused:
        # The door answers with its own dict, so the refusal is spliced here rather than in a
        # formatter: `refused` carries the current token and `needed`, on the tool door and
        # the HTTP door alike, because both return this value.
        return 409,identity_doors.refuse(
            {"error":"logical plan revision conflict","revision":current["revision"]},refused)
    operation=payload.get("operation");contract=logical_plan_operation_contract()
    rule=contract["operations"].get(operation)
    if not rule:return 422,{"error":"unknown logical plan operation"}
    missing=[key for key in rule["required"] if key not in payload]
    if missing:return 422,{"error":"logical_plan_change requires "+", ".join(missing)}
    for key in ("node","meaning","rationale","discharge_condition"):
        if key in rule["required"] and not str(payload.get(key) or "").strip():
            return 422,{"error":f"logical_plan_change {key} must not be empty"}
    net=_network(project,root);nodes=net.get("nodes") or {};relations,_rows=_relations(project,root,net)
    from laplace.research import corpus_ingest as ci
    by=payload.get("by") or "logical-plan"
    record=None
    if operation=="add_object":
        if payload.get("kind") not in ci.LOGICAL_KINDS:
            return 422,{"error":"unknown logical object kind"}
        record=ci.rewire_add(root,project,{"kind":"add-node","node":payload["node"],
            "node_kind":payload["kind"],"essence":payload["meaning"],"parent":payload.get("parent"),
            "ref":payload.get("source_ref"),"by":by})
        if record.get('error','').startswith(('ref.','ref[','ref ')):
            record={**record,'error':'source_ref'+record['error'][3:]}
    elif operation=="edit_meaning":
        record=ci.rewire_add(root,project,{"kind":"edit-essence","node":payload["node"],
            "value":payload["meaning"],"by":by})
    elif operation=="connect":
        if payload.get("relation")=="prerequisite" and (nodes.get(payload.get("target")) or {}).get("kind")=="citation":
            return 422,{"error":"A citation is a source identity, not a logical premise. Use support for source grounding, or connect to an explicit assumption/result with that source_ref."}
        record=ci.rewire_add(root,project,{"kind":"add-edge","node":payload["source"],
            "target":payload["target"],"rel":payload["relation"],
            "rationale":payload["rationale"],"by":by})
    elif operation=="add_obligation":
        error=_valid_target(payload.get("target"),nodes,relations)
        if error:return 422,{"error":error}
        if payload.get("work_kind") not in OBLIGATION_WORK_KINDS:
            return 422,{"error":"unknown obligation work_kind"}
        target=payload["target"];anchor=target.get("node_id") or target.get("source")
        obligation={"target":target,"work_kind":payload["work_kind"],
            "discharge_condition":str(payload["discharge_condition"]),"state":"open",
            "evidence":[],"disposition":""}
        record=ci.rewire_add(root,project,{"kind":"add-node","node":payload["node"],
            "node_kind":"question","essence":payload["meaning"],"target":anchor,"rel":"questions",
            "projection":{"obligation":obligation},"by":by})
    elif operation=="update_obligation":
        node=nodes.get(payload["node"]) or {};prior=(node.get("projection") or {}).get("obligation")
        if node.get("kind")!="question" or not isinstance(prior,dict):
            return 422,{"error":"update_obligation requires a current canonical question"}
        state_name=payload.get("state")
        if state_name not in OBLIGATION_STATES:return 422,{"error":"unknown obligation state"}
        evidence=payload.get("evidence",prior.get("evidence") or [])
        if not isinstance(evidence,list) or any(not isinstance(item,(str,dict)) or
                (isinstance(item,str) and not item.strip()) for item in evidence):
            return 422,{"error":"obligation evidence must be a list of exact non-empty references"}
        disposition=str(payload.get("disposition",prior.get("disposition") or "")).strip()
        if state_name in {"addressed","withdrawn"} and not evidence and not disposition:
            return 422,{"error":"addressed or withdrawn obligations require evidence or an explained disposition"}
        obligation={**prior,"state":state_name,"evidence":evidence,"disposition":disposition}
        if state_name in {"addressed","withdrawn"}:
            obligation["consumed_basis"]={**_obligation_basis(project,node,obligation,root,
                (net,relations,_rows),{}),"actor":by,"actor_source":"caller-supplied audit label",
                "authority":"canonical-question-projection","human_consent":"NOT_ESTABLISHED"}
        else:obligation.pop("consumed_basis",None)
        record=ci.rewire_add(root,project,{"kind":"set-projection","node":payload["node"],
            "value":{"obligation":obligation},"by":by})
    else:
        node=nodes.get(payload["node"]) or {};obligation=(node.get("projection") or {}).get("obligation")
        if node.get("kind")!="question" or not isinstance(obligation,dict):
            return 422,{"error":"route_obligation requires a current canonical question"}
        from laplace.work import project_work
        task_id="WORK-OBL-"+hashlib.sha256((project+":"+payload["node"]).encode()).hexdigest()[:16]
        specification={"id":task_id,"title":str(node.get("essence") or payload["node"]).split("\n")[0][:160],
            "goal":obligation["discharge_condition"],"kind":obligation["work_kind"],
            "obligation_id":payload["node"],"logical_target":obligation["target"],"origin":by}
        # Routing consumes the guarded question and creates its stable work once.
        # A later route selects that existing work; it does not acquire authority
        # to overwrite independently authored work or renew its acceptance.
        with project_work.dispatch_lock(root):
            prior=project_work._tasks(project,root).get(task_id)
            if prior:
                if prior.get("obligation_id")!=payload["node"]:
                    return 409,{"error":"The stable work identity belongs to another obligation; no work changed.",
                        "next_reads":[{"operation":"project","payload":{"view":"detail","id":task_id}}]}
                task=project_work.read(project,{"view":"detail","id":task_id},root)["task"]
                routing="EXISTING_WORK_PRESERVED"
            else:
                task=project_work.task(project,specification,root);routing="CREATED"
        state=logical_plan(project,focus=payload["node"],root=root)
        return 200,{"ok":True,"operation":operation,"task":task,"routing":routing,
            "work_read_handle":{"operation":"project","payload":{"view":"detail","id":task_id}},
            "work_edit":"Use task with the exact expected_work_revision from the focused work read; routing does not edit existing work.",
            "state":state,"revision":state.get("revision"),
            "next_guard":{"field":"base_revision","value":state.get("revision")}}
    if record.get("error"):return 422,{"error":record["error"]}
    state=logical_plan(project,focus=str(payload.get("node") or payload.get("source") or ""),root=root)
    return 200,{"ok":True,"operation":operation,"record":record["record"],
        "state":state,"revision":state.get("revision"),
        "next_guard":{"field":"base_revision","value":state.get("revision")}}


def operation_contract() -> dict:
    """The canonical concept-change payloads, shared by help and mutation."""
    from laplace.research.corpus_ingest import LOGICAL_KINDS
    from laplace.research import mathematical_records, engineering_support
    from laplace.pipeline.schema import (AXIS_NAMES, EDGE_RELATIONS, EPISTEMIC_STATUSES,
                                         PAIR_AXES, PROJECTION_SLOTS, RELATION_SEMANTICS)
    string={"type":"string","minLength":1}
    edge_axes=sorted(set(AXIS_NAMES)-set(PAIR_AXES))
    common={"project":string,"operation":{"enum":[]},
        "base_revision":{**string,"description":"Global concept graph revision; retained for compatibility and global operations."},
        "mutation_revision":{**string,"description":"Selected concept.context mutation_revision; stable across unrelated concept writes."},
        # The grammar's own identity field.  `base_revision` and `mutation_revision` are two
        # names for two DIFFERENT homes (concept-network and concept-node), which is why
        # "do not substitute a mutation_revision into base_revision" had to be said in prose;
        # a token carries its home, so the substitution is not expressible.
        "expected":identity_doors.EXPECTED_FIELD,
        "by":string}
    operations={
        "add_edge":{"required":["project","operation","base_revision","node","target","rel"],
            "properties":{**common,"node":string,"target":string,
                          "rel":{"enum":sorted(EDGE_RELATIONS)},"axis":{"enum":edge_axes},
                          "rationale":{"type":"string"}}},
        "remove_edge":{"required":["project","operation","base_revision","node","target"],
            "properties":{**common,"node":string,"target":string,
                          "rel":{"enum":sorted(EDGE_RELATIONS)}}},
        "retype_edge":{"required":["project","operation","base_revision","node","target","rel"],
            "properties":{**common,"node":string,"target":string,
                          "rel":{"enum":sorted(EDGE_RELATIONS)},"axis":{"enum":edge_axes},
                          "rationale":{"type":"string"}}},
        "edit_node":{"required":["project","operation","base_revision","node"],
            "requires_any":[["value","essence"]],
            "properties":{**common,"node":string,"value":{"type":"string"},
                          "essence":{"type":"string"}}},
        "add_node":{"required":["project","operation","base_revision","node"],
            "properties":{**common,"node":string,"node_kind":{"enum":list(LOGICAL_KINDS)},
                "essence":{"type":"string"},"parent":string,"target":string,
                "ref":mathematical_records.source_reference_schema(),
                "rel":{"enum":sorted(EDGE_RELATIONS)},"axis":{"enum":edge_axes},
                "supersedes":string}},
        "set_source":{"required":["project","operation","base_revision","node","value"],
            "properties":{**common,"node":string,"value":mathematical_records.source_replacement_schema()},
            "semantics":"Replace the full canonical source/ref locator list only. [] clears it explicitly. Existing mathematics.sources, scientific meaning, proof, status and relations remain. Each text locator must resolve; checksums use sha256, never # fragments."},
        "set_projection":{"required":["project","operation","base_revision","node","value"],
            "properties":{**common,"node":string,
                          "value":{"type":"object","additionalProperties":True,"properties":{"title":{"type":"string","maxLength":200},"engineering_support":engineering_support.binding_schema()}}},
            "semantics":"Merge authored projection metadata; optional title is a short scientific display title, separate from full essence and glossary term."},
        "set_mathematics":{"required":["project","operation","base_revision","node","value"],
            "properties":{**common,"node":string,"value":mathematical_records.schema()},
            "semantics":"Replace the authored mathematical record; other projection fields survive. Incomplete records remain visibly incomplete. Verification is derived from exact proof receipts, never supplied here."},
        "set_kind":{"required":["project","operation","base_revision","node","value"],
            "properties":{**common,"node":string,"value":{"enum":list(LOGICAL_KINDS)}}},
        "set_status":{"required":["project","operation","base_revision","node","value"],
            "properties":{**common,"node":string,"value":{"enum":list(EPISTEMIC_STATUSES)}},
            "model_allowed_values":["conjectured","exploratory"]},
        "set_spine":{"required":["project","operation","base_revision","node"],
            "properties":{**common,"node":string,"ord":{"type":"integer"},
                          "narrative":{"type":"string"}}},
        "unset_spine":{"required":["project","operation","base_revision","node"],
            "properties":{**common,"node":string}},
        "move_node":{"required":["project","operation","base_revision","node","target"],
            "properties":{**common,"node":string,"target":string}},
    }
    node_local={"edit_node","set_source","set_projection","set_mathematics",
                "set_kind","set_status"}
    for name,schema in operations.items():
        if name in node_local:
            schema["required"]=[key for key in schema["required"] if key!="base_revision"]
            schema.setdefault("requires_any",[]).append(["mutation_revision","base_revision"])
        schema["properties"]["operation"]={"const":next(
            key for key,value in operations.items() if value is schema)}
    return {"schema_version":"laplace.concept-change-contract/1",
            "logical_kinds":list(LOGICAL_KINDS),"edge_relations":sorted(EDGE_RELATIONS),
            "relation_semantics":RELATION_SEMANTICS,
            "edge_axes":edge_axes,"projection_slots":list(PROJECTION_SLOTS),
            "epistemic_statuses":list(EPISTEMIC_STATUSES),
            "revision_guards":{"mutation_revision":"Preferred for one-node content/source/kind/status operations; read concept.mutation_revision. It includes this node, its immediate relations, direct prerequisites and resolved source identities, but not unrelated graph edits.",
                "base_revision":"Exact global concept.revision. Required for node creation, relation, containment and spine changes; accepted for legacy one-node callers."},
            "operations":operations}


def _type_ok(value, expected) -> bool:
    choices=expected if isinstance(expected,list) else [expected]
    if "string" in choices and isinstance(value,str):return True
    if "object" in choices and isinstance(value,dict):return True
    if "integer" in choices and isinstance(value,int) and not isinstance(value,bool):return True
    if "array" in choices and isinstance(value,list):return True
    return False


def _validate_change(payload:dict) -> str|None:
    contract=operation_contract(); operation=payload.get("operation")
    schema=contract["operations"].get(operation)
    if schema is None:return "unknown operation"
    # A caller presenting its identity as a token in `expected` is not also asked for the old
    # name.  The list of old names is this door's shim and nothing else, so the schema cannot
    # drift from the gate that compares them.
    old=identity_doors.old_names("concept_change") if payload.get("expected") else frozenset()
    missing=[key for key in schema["required"] if key not in payload and key not in old]
    if missing:return "concept_change requires " + ", ".join(missing)
    for alternatives in schema.get("requires_any") or []:
        if old and set(alternatives) <= old:continue
        if not any(key in payload for key in alternatives):
            return "concept_change requires one of " + ", ".join(alternatives)
    if payload.get("mutation_revision") is not None and payload.get("base_revision") is not None:
        return "concept_change accepts one revision guard: mutation_revision or base_revision, not both"
    unknown=sorted(set(payload)-set(schema["properties"]))
    if unknown:return "concept_change contains unknown keys: " + ", ".join(unknown)
    for key,value in payload.items():
        rule=schema["properties"].get(key) or {}
        if "const" in rule and value!=rule["const"]:return f"concept_change.{key} must be {rule['const']!r}"
        if "enum" in rule and value not in rule["enum"]:return f"concept_change.{key} must be one of {rule['enum']}"
        if "type" in rule and not _type_ok(value,rule["type"]):return f"concept_change.{key} has the wrong type"
        if isinstance(value,str) and rule.get("minLength",0) and not value:return f"concept_change.{key} must not be empty"
    return None

def change(payload:dict,root:Path|None=None):
    try:identity_doors.admit_expected(payload, "concept_change")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    except identity_doors.IdentityRefused as refused:return 409,identity_doors.refuse({"error":str(refused)},refused)
    error=_validate_change(payload)
    if error:return 422,{"error":error}
    root=(root or _root()).resolve(); project=payload.get("project","");operation=payload.get("operation")
    local_guard=payload.get("mutation_revision") is not None
    focus=payload.get("node","") if local_guard else ""
    current=state(project,node=focus,root=root)
    if not current:return 404,{"error":"unknown project"}
    expected=payload.get("mutation_revision") if local_guard else payload.get("base_revision")
    guard="mutation_revision" if local_guard else "base_revision"
    said="mutation revision conflict" if local_guard else "revision conflict"
    # TWO names, TWO homes, one gate.  `mutation_revision` names `concept-node` (this node's
    # own content, concepts_surface.py:70-82) and `base_revision` names `concept-network` (the
    # whole graph, :20-22).  The door chose between them by hand and then published both
    # values back under their own names; the token says which home each value belongs to, so
    # "do not substitute a mutation_revision into base_revision" stops being prose
    # (writing_contracts.py:333) and becomes the home part of the token.
    def _gate(live):
        return identity_doors.gate(
            # THE CALLER'S OWN PAYLOAD, not a dict synthesised from one key.  A gate handed
            # `{guard: value}` can never see `expected`, so opening this door's schema to the
            # token field (:981, :1062) bought nothing a caller could use: `gate`'s
            # `raw_expected = supplied.get("expected")` was empty on every call.  Measured
            # 2026-10-02: `concept_change {expected:[<current concept-network token>], ...}`
            # was refused `revision conflict` while the same digest under `base_revision`
            # passed.  `payload.get(guard)` IS `expected` here, so the old names behave
            # exactly as before and `required=[guard]` is satisfied by a token for the same
            # home through `gate`'s `covered` set.
            "concept_change", supplied=payload,
            homes=[("concept-node","%s::%s"%(project,focus),live.get("content_revision"))]
                  if local_guard else
                  [("concept-network",project,live.get("revision"))],
            required=[guard],said=said)
    try:
        _gate(current)
    except identity_doors.IdentityRefused as refused:
        focused=current if local_guard else state(project,node=payload.get("node", ""),root=root)
        return 409,identity_doors.refuse({"error":said,
            "revision":current.get("revision"),"mutation_revision":(focused or {}).get("content_revision"),
            "recovery":{"operation":"concept","payload":{"node":payload.get("node")}}},refused)
    from laplace.research import corpus_ingest as ci
    mapping={"add_edge":"add-edge","remove_edge":"remove-edge","retype_edge":"retype-edge","edit_node":"edit-essence","add_node":"add-node","set_projection":"set-projection","set_mathematics":"set-projection","set_kind":"set-kind","set_status":"set-status","set_spine":"set-spine","unset_spine":"unset-spine","move_node":"move-node","set_source":"set-source"}
    kind=mapping[operation]
    if kind == "set-status" and str(payload.get("by") or "").startswith("eigen:"):
        from laplace.pipeline.schema import canonical_status
        if canonical_status(payload.get("value")) in {"proven", "computed", "imported"}:
            return 403,{"error":"a producing model cannot award proven, computed, or imported epistemic status"}
    value=payload.get("value") if "value" in payload else payload.get("essence") if kind=="edit-essence" else None
    if operation=="set_projection" and "title" in value and (not isinstance(value["title"],str) or len(value["title"])>200):
        return 422,{"error":"projection.title must be text of at most 200 characters; use empty text to clear it"}
    if operation=="set_mathematics" or (operation=="set_projection" and "mathematics" in value):
        from laplace.research import mathematical_records
        nodes=(_network(project,root) or {}).get("nodes",{})
        if payload["node"] not in nodes:return 404,{"error":"unknown concept node"}
        mathematics=value if operation=="set_mathematics" else value["mathematics"]
        try:mathematical_records.validate(mathematics,nodes)
        except ValueError as exc:return 422,{"error":str(exc)}
        if operation=="set_mathematics":value={"mathematics":mathematics}
    def engineering_precondition(live):
        if operation != 'set_projection' or 'engineering_support' not in value:
            return None
        from laplace.research import engineering_support
        if set(value) != {'engineering_support'}:
            return {'error':'Adopt engineering support separately from meaning or other projection edits'}
        try:
            engineering_support.validate_adoption(project,payload['node'],root,
                _network(project,root),value['engineering_support'])
        except (ValueError,OSError,TypeError) as exc:
            return {'error':str(exc)}
        return None
    adoption_error=engineering_precondition(current)
    if adoption_error:return 422,adoption_error
    def mutation_precondition():
        live=state(project,node=payload.get("node","") if local_guard else "",root=root)
        if not live:return {"error":"unknown project or concept node","conflict":True}
        # The precondition inside the writer's lock is THE SAME gate, not a second
        # comparison written out again: one function, so the door and its precondition
        # cannot drift the way the roster at review_surface.py:1253-1257 drifted from the
        # one the executor docstring at :1394-1397 calls "the ONE roster".
        try:
            _gate(live)
            return engineering_precondition(live)
        except identity_doors.IdentityRefused as refused:
            focused=live if local_guard else state(project,node=payload.get("node", ""),root=root)
            return identity_doors.refuse({"error":said,
                "conflict":True,"revision":live.get("revision"),
                "mutation_revision":(focused or {}).get("content_revision"),
                "recovery":{"operation":"concept","payload":{"node":payload.get("node")}}},refused)
    record=ci.rewire_add(root,project,{"kind":kind,"node":payload.get("node"),"target":payload.get("target"),"value":value,"essence":payload.get("essence"),"parent":payload.get("parent"),"ref":payload.get("ref"),"ord":payload.get("ord"),"narrative":payload.get("narrative"),"node_kind":payload.get("node_kind"),"rel":payload.get("rel"),"axis":payload.get("axis"),"rationale":payload.get("rationale"),"supersedes":payload.get("supersedes"),"by":payload.get("by","concepts")},precondition=mutation_precondition)
    if record.get("error"):
        return (409 if record.get("conflict") else 422),record
    return 200,{"ok":True,"record":record["record"],
        **({"effects":["concepts","references","structure","research","proofs","pipeline"]} if operation=="set_source" else {}),
        "state":state(project,node=payload.get("node", ""),root=root)}

_SOURCE_LOCATION_KEYS=("reference","status","repository","path","label","file","sha256",
                       "line_start","line_end","environment","truncated","error")


def _context_source_location(row:dict) -> dict:
    """One traceable locator; source bodies descend through /concepts/source."""
    return {key:row.get(key) for key in _SOURCE_LOCATION_KEYS if row.get(key) is not None}


def _context_projection(value:dict) -> dict:
    """Bounded agent read of one canonical object without duplicating its science.

    The UI/full-state route remains :func:`state`.  This projection carries the
    exact statement, assumptions and proof once, and keeps source locations as
    identities.  Following ``source_body`` is the explicit body-read operation.
    """
    node=dict(value.get("focus") or {})
    projection=dict(node.get("projection") or {})
    projection.pop("mathematics",None)
    node["projection"]=projection
    node.pop("source",None)
    if node.get("label")==node.get("summary"):
        node.pop("label",None)
    record=dict(value.get("mathematical_record") or {})
    authored=dict(record.pop("authored",{}) or {})
    locations=[_context_source_location(row) for row in
               (record.get("source_locations") or value.get("source_locations") or [])
               if isinstance(row,dict)]
    record.pop("source_locations",None)
    if authored:
        record["authored_fields"]=sorted(authored)
        record["authored_source_count"]=len(authored.get("sources") or [])
        if isinstance(authored.get("primary_source"),int):
            record["authored_primary_source"]=authored["primary_source"]
    dependencies=list(value.get("relations") or [])
    neighbors={row.get("id"):row for row in value.get("neighbors") or [] if row.get("id")}
    prerequisites=[]
    for relation in dependencies:
        if relation.get("rel")!="prerequisite" or relation.get("source")!=node.get("id"):
            continue
        target=relation.get("target");neighbor=neighbors.get(target) or {}
        prerequisites.append({"id":target,"title":neighbor.get("title"),
            "label":neighbor.get("label"),"kind":neighbor.get("kind"),
            "status":neighbor.get("status"),"relation":"prerequisite",
            "rationale":relation.get("rationale"),
            "read":{"operation":"concept","payload":{"node":target}}})
    spine=list(value.get("spine") or [])
    return {"schema_version":"laplace.concept-context/2",
        "project":value.get("project"),"revision":value.get("revision"),
        # The bounded read reprojects a fixed key list, so the token has to be carried across
        # explicitly or the caller that uses THIS read (the one the contract routes it to) never
        # sees a home name at all.
        "identities":value.get("identities") or {},
        "mutation_revision":value.get("content_revision"),
        "content_revision":value.get("content_revision"),"node":node,
        "mathematical_record":record or None,
        "source_locations":locations,"source_support":value.get("source_support"),
        "dependencies":dependencies,"prerequisites":prerequisites,
        "spine_membership":[row for row in spine if
            row==node.get("id") or isinstance(row,dict) and row.get("id")==node.get("id")],
        "spine_total":len(spine),
        "read_routes":{"source_body":{"operation":"concept",
            "payload":{"node":node.get("id"),"source_index":"<source_index>"}},
            "history":{"operation":"concept_history","payload":{"node":node.get("id")}},
            "tree":{"operation":"concept_tree","payload":{"node":node.get("id")}}},
        "prompt":"Read the exact statement, assumptions, proof, source locators, qualification and prerequisite requirements before writing. Follow source_body for actual source text. Relations are structure; metadata and analogy are not entailment."}


def context(project:str,node:str,root:Path|None=None,*,read_context=None):
    value=state(project,node,root=root,read_context=read_context)
    if not value:return None
    return _context_projection(value)


def source_reference(project:str,node:str,source_index:int,label:str="",root:Path|None=None):
    """Follow a reference within an already recorded concept source."""
    from laplace.research import mathematical_records
    root=(root or _root()).resolve()
    value=state(project,node,root=root)
    if not value:return None
    sources=(value.get("mathematical_record") or {}).get("source_locations") or []
    if source_index<0 or source_index>=len(sources):
        raise ValueError("Choose a recorded source from the current concept read")
    reference=sources[source_index].get("reference")
    if label:
        if len(label)>256 or any(char in label for char in "{}\n\r"):
            raise ValueError("The source label is invalid")
        if isinstance(reference,str):reference=reference.partition("#")[0]+"#"+label
        elif isinstance(reference,dict):
            reference={key:item for key,item in reference.items() if key not in {"line","line_start","line_end"}}
            reference["label"]=label
    return {"project":project,"node":node,"source_index":source_index,
            **mathematical_records.resolve_source(project,reference,root)}

def handle(path:str,query:dict,method:str,body:bytes,repo_root=None):
    if path!="/concepts" and not path.startswith("/concepts/"):return None
    m=(method or "GET").upper(); project=_q(query,"project")
    if path=="/concepts/source" and m=="GET":
        try:out=source_reference(project,_q(query,"node"),int(_q(query,"source_index") or 0),_q(query,"label"),root=repo_root)
        except ValueError as exc:return _resp(422,{"error":str(exc)})
        return _resp(200,out) if out is not None else _resp(404,{"error":"unknown concept"})
    if path=="/concepts/catalog" and m=="GET":
        try:out=catalog(project,_q(query,'q'),int(_q(query,'offset') or 0),int(_q(query,'limit') or 80),root=repo_root)
        except ValueError as exc:return _resp(422,{'error':str(exc)})
        if out is None and (known:=logical_plan_availability(project,repo_root)) and not known["available"]:
            return _resp(200,{**known,"requested":{"view":"catalog"}})
        return _resp(200,out) if out is not None else _resp(404,{'error':'unknown project'})
    if path=="/concepts/tree" and m=="GET":
        allowed=set(tree_contract()["properties"])
        unknown=sorted(set(query)-allowed)
        if unknown:return _resp(422,{"error":"concept_tree contains unknown query keys: "+", ".join(unknown)})
        try:out=tree(project,_q(query,"node"),int(_q(query,"offset") or 0),
                     int(_q(query,"limit") or 40),int(_q(query,"uncontained_offset") or 0),int(_q(query,"dependency_offset") or 0),
                     int(_q(query,"dependency_limit") or 80),root=repo_root,
                     direction=_q(query,"direction") or "current",from_node=_q(query,"from"),
                     goal=_q(query,"goal"))
        except ValueError as exc:return _resp(422,{"error":str(exc)})
        return _resp(200,out) if out else _resp(404,{"error":"unknown project or concept node"})
    if path=="/concepts/state" and m=="GET":
        out=state(project,_q(query,"node"),_q(query,"q"),root=repo_root); return _resp(200,out) if out else _resp(404,{"error":"unknown project"})
    if path=="/concepts/history" and m=="GET":
        try:out=history(project,_q(query,"node"),int(_q(query,"offset") or 0),
                        int(_q(query,"limit") or 12),_q(query,"record"),root=repo_root)
        except ValueError as exc:return _resp(422,{"error":str(exc)})
        return _resp(200,out) if out else _resp(404,{"error":"unknown project or logical object"})
    if path=="/concepts/plan" and m=="GET":
        try:out=logical_plan(project,_q(query,"focus"),int(_q(query,"offset") or 0),
                             int(_q(query,"limit") or 200),root=repo_root)
        except ValueError as exc:return _resp(422,{"error":str(exc)})
        if not out and (known:=logical_plan_availability(project,repo_root)) and not known["available"]:
            return _resp(200,{**known,"requested":{"focus":_q(query,"focus")}})
        return _resp(200,out) if out else _resp(404,{"error":"unknown project"})
    if path=="/concepts/plan/context" and m=="GET":
        try:out=logical_plan_context(project,_q(query,"node"),root=repo_root,
            file=_q(query,"file"),line_start=int(_q(query,"line_start") or 0),
            line_end=int(_q(query,"line_end") or 0),
            accepted_offset=int(_q(query,"accepted_offset") or 0),accepted_limit=int(_q(query,"accepted_limit") or 40),
            accepted_as_of=_q(query,"accepted_as_of"))
        except ValueError as exc:return _resp(422,{"error":str(exc)})
        if not out and (known:=logical_plan_availability(project,repo_root)) and not known["available"]:
            return _resp(200,{**known,"requested":{"node":_q(query,"node")}})
        return _resp(200,out) if out else _resp(404,{"error":"unknown project or logical object"})
    if path=="/concepts/plan/change" and m=="POST":
        try:p=json.loads(body or b"{}")
        except ValueError:return _resp(400,{"error":"bad json"})
        s,out=logical_plan_change(p,root=repo_root) if isinstance(p,dict) else (400,{"error":"body must be object"})
        return _resp(s,out)
    if path=="/concepts/context" and m=="GET":
        out=context(project,_q(query,"node"),root=repo_root); return _resp(200,out) if out else _resp(404,{"error":"unknown project"})
    if path=="/concepts/change" and m=="POST":
        try:p=json.loads(body or b"{}")
        except ValueError:return _resp(400,{"error":"bad json"})
        s,out=change(p,root=repo_root) if isinstance(p,dict) else (400,{"error":"body must be object"});return _resp(s,out)
    return _resp(405,{"error":"unsupported concepts route"})


# TRUTHFUL LOGICAL-PLAN AVAILABILITY (campaign bounded source reading, 2026-10-14). Appended at the end so
# no cited line of this owner moves.
def logical_plan_availability(project:str,root:Path|None=None) -> dict|None:
    """Whether this project HAS a logical plan, said truthfully.

    None for an unknown project and for every layout other than a registered source-optional
    project: their existing answers (refusal, paper plan semantics) stand.  A registered
    source-optional project is outside the conceptric corpus layout, so it has no logical-plan
    (concept graph) owner, whether or not a manuscript is selected (repair1 R3: the selected
    manuscript is reported separately and nothing promises that starting one creates a plan).
    The reads say so in a bounded 200 answer that names the owners the project does have.
    Nothing is created; no permission or concept gate changes.
    """
    root=(root or _root()).resolve()
    from laplace.pipeline import registry
    from laplace.research import corpus_ingest as ci
    from laplace.manuscript import manuscript_source
    record=registry.resolve(project,root)
    if record is None or getattr(record,'kind','')!='project':return None
    if ci.resolve_corpus(root,project):return {"status":"AVAILABLE","available":True}
    selected=manuscript_source.resolve(project,repo_root=root)
    status=selected.get("status") or "unknown"
    manuscript={"status":status,"selected":status=="resolved",
                **({"read_only":bool(selected.get("read_only"))} if status=="resolved" else {})}
    from laplace.projects import project_lifecycle
    lifecycle=project_lifecycle.observe(project,root)
    reason=("This registered source-optional project has no logical-plan (concept graph) owner yet: it has not started its "
            "reader/argument plan. "
            +("Its selected manuscript is readable through the manuscript and source readers; " if status=="resolved" else "It has no selected manuscript; ")
            +"this is a known project, not an unknown-project refusal.")
    return {"schema_version":"laplace.logical-plan-availability/2","project":project,
            "status":"NOT_AVAILABLE","available":False,"layout":"project","source_optional":True,
            "logical_plan_owner":None,"manuscript":manuscript,"reason":reason,
            "items":[],"total":0,"selected":None,
            "supported_reads":[
                {"operation":"research","payload":{"view":"summary"},"says":"recorded results, experiments and their evidence"},
                {"operation":"material_references","payload":{"view":"list"},"says":"linked shared material; a JSON source reads one record with pointer"},
                {"operation":"read_artifact","payload":{"path":"<artifact path>","scope":"project"},"says":"project artifacts; a JSON artifact reads one record with pointer"},
                {"operation":"project_metadata","payload":{},"says":"display title, selected-source facts and capabilities"}],
            "creates_a_plan":("This read creates nothing. structure_change start_authoring (the guarded next action below, from "
                              "project_metadata.authoring_lifecycle) starts the manuscript if needed and declares the reader/argument "
                              "plan owner; structure_change initialize then creates the plan."),
            "next_action":lifecycle["next_action"],"authoring_state":lifecycle["state"],
            "write_permission":False}


def _no_plan_to_change(project:str,root:Path) -> tuple[int,dict]:
    """The change owner's refusal when no plan exists: still refused, and truthful about a known project."""
    known=logical_plan_availability(project,root) if project else None
    if known and not known["available"]:
        return 404,{"error":"No logical plan exists to change: "+known["reason"],"status":known["status"],"supported_reads":known["supported_reads"]}
    return 404,{"error":"unknown project"}
